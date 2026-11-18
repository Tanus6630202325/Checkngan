import json
import re
import time

import httpx

BASE = "https://www.jobthai.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "th,en;q=0.8",
}
NEXT_DATA = re.compile(r'__NEXT_DATA__[^>]*>(.*?)</script>', re.S)


def _parse(html: str, keyword: str = "") -> list[dict]:
    m = NEXT_DATA.search(html)
    if not m:
        return []
    root = json.loads(m.group(1))["props"]["apolloState"]["ROOT_QUERY"]
    key = next((k for k in root if k.startswith("searchJobs")), None)
    if not key:
        return []
    # ถ้าเว็บตอบผลที่ไม่ได้กรองตามคำค้น (เกิดเป็นบางครั้ง) ให้ทิ้งผลนั้น
    if keyword and json.dumps(keyword, ensure_ascii=False) not in key:
        return []
    jobs = []
    for it in root[key]["data"]["data"]:
        place = " ".join(
            x for x in [(it.get("district") or {}).get("name"), (it.get("province") or {}).get("name")] if x
        )
        jobs.append({
            "source": "jobthai",
            "job_id": str(it["id"]),
            "title": it["jobTitle"],
            "company": it.get("companyName"),
            "location": place or None,
            "salary": it.get("salary"),
            "job_type": (it.get("jobType") or {}).get("name"),
            "raw_category": (it.get("jobType") or {}).get("name"),
            "logo": f"https://media.jobthai.com/v1/images/{it['companyLogo']}" if it.get("companyLogo") else None,
            "url": f"{BASE}/th/job/{it['id']}",
            "posted_at": it.get("updatedAt"),
        })
    return jobs


def scrape(keyword: str = "", pages: int = 3) -> list[dict]:
    out = []
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        for page in range(1, pages + 1):
            r = client.get(f"{BASE}/th/jobs", params={"keyword": keyword, "page": page})
            r.raise_for_status()
            jobs = _parse(r.text, keyword)
            if not jobs:
                break
            out += jobs
            time.sleep(1.5)  # ไม่ยิงรัวเกินไป
    return out
