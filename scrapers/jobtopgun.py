import re
import time
from urllib.parse import unquote

import httpx
from bs4 import BeautifulSoup

BASE = "https://www.jobtopgun.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "th,en;q=0.8",
}
JOB_HREF = re.compile(r"^/th/jobs/(j[\w-]+)$")


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for card in soup.select("article[aria-label]"):
        a = card.find("a", href=JOB_HREF)
        if not a:
            continue
        job_id = JOB_HREF.match(a["href"]).group(1)
        h2 = card.find("h2")
        parts = list(card.stripped_strings)
        # โลโก้อยู่ใน srcSet ของ next/image เป็น url=<encoded> ดึงต้นฉบับออกมา
        logo = None
        img = card.find("img", srcset=True)
        if img:
            m = re.search(r"url=([^&\s]+)", img["srcset"])
            if m:
                logo = unquote(m.group(1))
        # โครงสร้างการ์ด: ชื่องาน | บริษัท | สถานที่ | ประเภทงาน | ...
        jobs.append({
            "source": "jobtopgun",
            "job_id": job_id,
            "title": (h2 or a).get_text(strip=True),
            "company": parts[1] if len(parts) > 1 else None,
            "location": parts[2] if len(parts) > 2 else None,
            "salary": None,  # หน้ารายการไม่แสดงเงินเดือน
            "job_type": parts[3] if len(parts) > 3 else None,
            "url": BASE + a["href"],
            "posted_at": None,  # หน้ารายการมีแค่ "4 วันที่แล้ว"
            "logo": logo,
        })
    return jobs


def scrape(keyword: str = "", pages: int = 3) -> list[dict]:
    out = []
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        for page in range(1, pages + 1):
            r = client.get(f"{BASE}/th/jobs", params={"keyword": keyword, "page": page})
            r.raise_for_status()
            jobs = _parse(r.text)
            if not jobs:
                break
            out += jobs
            time.sleep(1.5)
    return out
