"""วิเคราะห์เรซูเม่ด้วย Claude แล้วจับคู่กับงานในฐานข้อมูล

ขั้นตอน: (1) สรุปโปรไฟล์จากเรซูเม่  (2) ดึงงานที่น่าจะเข้าจากฐานข้อมูล  (3) ให้ Claude ให้คะแนนแต่ละงาน
เรซูเม่ไม่ถูกบันทึกลงดิสก์/ฐานข้อมูล ส่งไปที่ Groq API เท่านั้น
ใช้ Groq (OpenAI-compatible REST) ผ่าน httpx ตรงๆ ไม่ต้องติดตั้ง SDK เพิ่ม
"""
import io
import json
import os
import re
import time
from pathlib import Path

import httpx

import db
from categories import ALL as CATEGORIES

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
MAX_FILE_MB = 10


class MatchError(Exception):
    """ข้อผิดพลาดที่แสดงให้ผู้ใช้อ่านได้"""


def load_env():
    """อ่าน .env แบบง่ายๆ (KEY=VALUE) ถ้ายังไม่ได้ตั้ง environment variable"""
    path = Path(__file__).parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if v and not os.environ.get(k):  # ไม่ทับค่าที่ตั้งไว้แล้ว แต่ข้ามค่าว่าง
                os.environ[k] = v


def _api_key() -> str:
    load_env()
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise MatchError(
            "ยังไม่ได้ตั้ง GROQ_API_KEY — ใส่ในไฟล์ .env เป็น GROQ_API_KEY=gsk_... แล้วรีสตาร์ท server"
        )
    return key


def _duration(text: str) -> float | None:
    """แปลงข้อความเวลาแบบ Groq เช่น '13.6s', '1m5.2s', '4m19s' เป็นวินาที"""
    m = re.fullmatch(r"(?:(\d+)m)?(?:([\d.]+)s)?", text.strip())
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 60 + float(m.group(2) or 0)


def _retry_wait(r: httpx.Response) -> float:
    """เวลาที่ควรรอก่อนลองใหม่ จาก header ของ Groq (retry-after หรือเวลารีเซ็ตโควต้าโทเคน)"""
    ra = r.headers.get("retry-after")
    if ra and ra.replace(".", "", 1).isdigit():
        return float(ra) + 1
    d = _duration(r.headers.get("x-ratelimit-reset-tokens", ""))
    return (d if d is not None else 15) + 1


def _ask(key: str, system: str, user: str, schema: dict, name: str) -> dict:
    """เรียก Groq ให้ตอบเป็น JSON ตาม schema (ถ้า strict schema ไม่รองรับ จะถอยไปใช้ json_object)"""
    def call(response_format, sys_prompt):
        for attempt in range(4):
            r = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": MODEL,
                    "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}],
                    "response_format": response_format,
                    "reasoning_effort": "medium",
                    "max_completion_tokens": 5000,
                    "temperature": 0.2,
                },
                timeout=120,
            )
            if r.status_code != 429:
                return r
            wait = _retry_wait(r)
            if attempt == 3 or wait > 60:  # รอนานเกิน (น่าจะเป็นโควต้ารายวัน) ไม่รอแล้ว
                return r
            time.sleep(wait)  # โควต้ารายนาทีเต็ม: รอให้รีเซ็ตแล้วลองใหม่
        return r

    try:
        r = call({"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}, system)
        if r.status_code == 400:
            fallback = system + "\n\nตอบเป็น JSON เท่านั้น ตาม schema นี้:\n" + json.dumps(schema, ensure_ascii=False)
            r = call({"type": "json_object"}, fallback)
    except httpx.TimeoutException:
        raise MatchError("Groq ตอบช้าเกินไป ลองใหม่อีกครั้ง")
    except httpx.HTTPError:
        raise MatchError("เชื่อมต่อ Groq ไม่ได้ ตรวจสอบอินเทอร์เน็ต")
    if r.status_code == 401:
        raise MatchError("GROQ_API_KEY ไม่ถูกต้อง ตรวจสอบค่าในไฟล์ .env")
    if r.status_code == 429:
        raise MatchError(
            f"โควต้า Groq เต็ม (ฟรีจำกัด 8,000 โทเคน/นาที และมีโควต้ารายวัน) — ลองใหม่อีกครั้งในอีก ~{int(_retry_wait(r))} วินาที"
        )
    if r.status_code != 200:
        raise MatchError(f"Groq error {r.status_code}: {r.text[:200]}")
    choice = r.json()["choices"][0]
    if choice.get("finish_reason") == "length":
        raise MatchError("ผลลัพธ์ยาวเกินไป ลองใหม่อีกครั้ง")
    try:
        return json.loads(choice["message"]["content"])
    except (json.JSONDecodeError, TypeError):
        raise MatchError("AI ตอบรูปแบบไม่ถูกต้อง ลองใหม่อีกครั้ง")


# ---------- อ่านไฟล์เรซูเม่ (ดึงเป็นข้อความ เพราะโมเดลที่ใช้อ่านได้เฉพาะข้อความ) ----------
def resume_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise MatchError(f"ไฟล์ใหญ่เกิน {MAX_FILE_MB} MB")
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        try:
            text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        except Exception:
            raise MatchError("เปิดไฟล์ PDF ไม่ได้ (ไฟล์เสียหรือมีรหัสผ่าน?)")
        if len(text.strip()) < 50:
            raise MatchError("PDF นี้เป็นรูปสแกน อ่านข้อความไม่ได้ — ลองส่งเป็น .docx/.txt หรือ PDF ที่เลือกข้อความได้")
    elif ext == ".docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            parts += [c.text for row in t.rows for c in row.cells]
        text = "\n".join(x for x in parts if x.strip())
    elif ext in (".txt", ".md"):
        text = data.decode("utf-8", errors="ignore")
    else:
        raise MatchError("รองรับเฉพาะไฟล์ .pdf .docx .txt")
    if len(text.strip()) < 30:
        raise MatchError("อ่านข้อความจากไฟล์ไม่ได้ (ว่างเปล่า?)")
    return text[:30000]


# ---------- ขั้นที่ 1: สรุปโปรไฟล์ ----------
PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "current_or_recent_title": {"type": "string"},
        "level": {"type": "string", "enum": ["นักศึกษา/จบใหม่", "จูเนียร์", "มิดเลเวล", "ซีเนียร์", "หัวหน้า/ผู้จัดการขึ้นไป"]},
        "years_experience": {"type": "number"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "suitable_categories": {"type": "array", "items": {"type": "string", "enum": CATEGORIES}},
        "search_keywords": {"type": "array", "items": {"type": "string"}},
        "preferred_locations": {"type": "array", "items": {"type": "string"}},
        "expected_salary_min": {"type": "integer"},
        "expected_salary_max": {"type": "integer"},
        "salary_reasoning": {"type": "string"},
    },
    "required": ["summary", "current_or_recent_title", "level", "years_experience", "skills",
                 "suitable_categories", "search_keywords", "preferred_locations",
                 "expected_salary_min", "expected_salary_max", "salary_reasoning"],
    "additionalProperties": False,
}

PROFILE_SYSTEM = (
    "คุณเป็นที่ปรึกษาด้านอาชีพในตลาดงานไทย อ่านเรซูเม่แล้วสรุปโปรไฟล์ผู้สมัครเป็น JSON "
    "ตอบเป็นภาษาไทย (ชื่อทักษะ/เทคโนโลยีใช้ตามเดิม) "
    "search_keywords ให้ 6-12 คำที่ใช้ค้นชื่อตำแหน่งงานได้จริง ทั้งภาษาไทยและอังกฤษ เช่น 'Python', 'นักวิเคราะห์ข้อมูล' "
    "suitable_categories เลือก 1-3 หมวดที่เหมาะที่สุดเท่านั้น "
    "preferred_locations ใส่เฉพาะที่เรซูเม่ระบุหรือบ่งชี้ชัด ถ้าไม่มีให้เป็นลิสต์ว่าง "
    "expected_salary_min/max คือช่วงเงินเดือนต่อเดือนเป็นบาท ที่เหมาะสมกับผู้สมัครคนนี้ในตลาดงานไทยตอนนี้ "
    "ประเมินจากตำแหน่ง ทักษะ จำนวนปีประสบการณ์ และระดับ ไม่ใช่เงินเดือนที่ผู้สมัครเคยได้ "
    "ให้ช่วงแคบพอใช้ได้จริง (ค่าสูงไม่เกิน 1.6 เท่าของค่าต่ำ) ปัดเป็นหลักพัน "
    "salary_reasoning ให้ 1-2 ประโยค บอกปัจจัยที่ใช้ประเมิน และถ้าข้อมูลในเรซูเม่น้อยจนประเมินไม่แน่นอน ให้บอกตรงๆ "
    "ห้ามใส่ชื่อ เบอร์โทร อีเมล หรือที่อยู่ของผู้สมัครในผลลัพธ์"
)


def analyze_profile(key: str, text: str) -> dict:
    return _ask(key, PROFILE_SYSTEM, "เรซูเม่:\n\n" + text, PROFILE_SCHEMA, "profile")


# ---------- ขั้นที่ 3: จัดอันดับงาน ----------
RANK_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                    "gaps": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["n", "score", "reason", "gaps"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["matches"],
    "additionalProperties": False,
}

RANK_SYSTEM = (
    "คุณเป็นที่ปรึกษาด้านอาชีพ ให้คะแนนความเหมาะสมของผู้สมัครกับงานแต่ละตำแหน่ง (0-100) "
    "โดยดูทักษะ ระดับประสบการณ์ ทิศทางอาชีพ และสถานที่ ตอบเป็นภาษาไทย "
    "ข้อมูลงานมีแค่ชื่อตำแหน่ง บริษัท สถานที่ หมวด เงินเดือน (ไม่มีรายละเอียดคุณสมบัติ) "
    "จึงให้ประเมินจากชื่อตำแหน่งเป็นหลัก และอย่าอ้างคุณสมบัติที่ข้อมูลไม่ได้ระบุ "
    "ให้คะแนนตรงไปตรงมา ไม่ต้องเอาใจ ตำแหน่งที่ไม่เกี่ยวควรได้คะแนนต่ำ "
    "เลือกเฉพาะ 20 งานที่เหมาะที่สุด เรียงจากมากไปน้อย; n คือหมายเลขงานในรายการ; "
    "reason 1 ประโยคสั้นๆ; gaps คือทักษะ/ประสบการณ์ที่น่าจะต้องเพิ่ม (ว่างได้ ไม่เกิน 3 ข้อ)"
)


def rank_jobs(key: str, profile: dict, jobs: list[dict]) -> list[dict]:
    lines = [
        f"{i}. {j['title']} | {j['company'] or '-'} | {j['location'] or '-'} | "
        f"{j['category'] or '-'} | {j['salary'] or '-'}"
        for i, j in enumerate(jobs, 1)
    ]
    prompt = (
        "โปรไฟล์ผู้สมัคร:\n" + json.dumps(profile, ensure_ascii=False, indent=1)
        + "\n\nรายการงาน:\n" + "\n".join(lines)
    )
    result = _ask(key, RANK_SYSTEM, prompt, RANK_SCHEMA, "ranking")
    out = []
    for m in result["matches"]:
        if 1 <= m["n"] <= len(jobs):
            out.append({**jobs[m["n"] - 1], "score": max(0, min(100, m["score"])),
                        "reason": m["reason"], "gaps": m["gaps"][:3]})
    out.sort(key=lambda x: -x["score"])
    return out[:20]


_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kK])?")
_NOT_MONTHLY = re.compile(r"per\s*(hour|day|week|year|annum)|/\s*(hr|hour|day|year)|ชั่วโมง|ต่อวัน|รายวัน|ต่อปี|\$|usd", re.I)


def parse_salary(text: str | None):
    """แปลงข้อความเงินเดือนเป็น (ต่ำสุด, สูงสุด) บาท/เดือน; คืน None ถ้าไม่ใช่เงินเดือนรายเดือนที่ระบุตัวเลข"""
    if not text or _NOT_MONTHLY.search(text):
        return None
    found = [(float(n.replace(",", "")), bool(k)) for n, k in _NUM.findall(text)]
    if any(k for _, k in found):  # "30-50K" -> K ใช้กับทั้งช่วง
        found = [(v * 1000 if (k or v < 1000) else v, k) for v, k in found]
    vals = [v for v, _ in found if 5000 <= v <= 500000]  # ตัดตัวเลขที่ไม่น่าใช่เงินเดือน
    if not vals:
        return None
    return min(vals[:2]), max(vals[:2])


def _market_stats(jobs: list[dict]):
    mids = sorted((lo + hi) / 2 for lo, hi in filter(None, (parse_salary(j.get("salary")) for j in jobs)))
    n = len(mids)
    if n == 0:
        return None
    q = lambda p: mids[min(n - 1, int(p * (n - 1) + 0.5))]
    return {"n": n, "p25": round(q(0.25), -3), "median": round(q(0.5), -3),
            "p75": round(q(0.75), -3), "min": round(mids[0], -3), "max": round(mids[-1], -3)}


def market_salary(matches: list[dict], candidates: list[dict]):
    """สถิติเงินเดือนจากงานที่เหมาะที่สุดก่อน ถ้าตัวอย่างน้อยกว่า 3 งานค่อยถอยไปใช้งานใกล้เคียงทั้งหมด"""
    good = _market_stats([m for m in matches if m["score"] >= 50])
    if good and good["n"] >= 3:
        return {**good, "basis": "งานที่เหมาะกับคุณ (คะแนน ≥ 50%) ที่ระบุเงินเดือน"}
    wide = _market_stats(candidates)
    if wide and wide["n"] >= 3:
        return {**wide, "basis": "งานใกล้เคียงทั้งหมดที่ระบุเงินเดือน (ตัวอย่างงานที่เหมาะมากมีน้อย)"}
    return None


def _clean_salary_estimate(profile: dict):
    lo, hi = profile.get("expected_salary_min") or 0, profile.get("expected_salary_max") or 0
    if lo > hi:
        lo, hi = hi, lo
    if hi <= 0:
        profile["expected_salary_min"] = profile["expected_salary_max"] = None
    else:
        profile["expected_salary_min"], profile["expected_salary_max"] = lo, hi


def match_resume(filename: str, data: bytes, location: str = "") -> dict:
    key = _api_key()
    profile = analyze_profile(key, resume_text(filename, data))
    if location:
        profile["preferred_locations"] = [location]
    jobs = db.candidate_jobs(profile["suitable_categories"], profile["search_keywords"],
                             profile["preferred_locations"], limit=60)
    if not jobs:
        raise MatchError("ไม่พบงานในฐานข้อมูลที่ใกล้เคียง ลองกด “ดึงงานใหม่” ก่อน")
    _clean_salary_estimate(profile)
    matches = rank_jobs(key, profile, jobs)
    return {"profile": profile, "candidates": len(jobs), "matches": matches,
            "market": market_salary(matches, jobs)}
