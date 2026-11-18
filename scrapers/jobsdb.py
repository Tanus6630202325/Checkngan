import json
import re
import time

import httpx

BASE = "https://th.jobsdb.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "th,en;q=0.8",
}
MARKER = "SEEK_REDUX_DATA = "


def _parse(html: str) -> list[dict]:
    i = html.find(MARKER)
    if i < 0:
        return []
    data, _ = json.JSONDecoder().raw_decode(html[i + len(MARKER):])
    jobs = []
    for it in data.get("results", {}).get("results", {}).get("jobs", []):
        jobs.append({
            "source": "jobsdb",
            "job_id": str(it["id"]),
            "title": it["title"],
            "company": it.get("companyName") or (it.get("advertiser") or {}).get("description"),
            "location": ", ".join(l["label"] for l in it.get("locations", [])) or None,
            "salary": it.get("salaryLabel") or None,
            "job_type": ", ".join(it.get("workTypes", [])) or None,
            "logo": (it.get("branding") or {}).get("serpLogoUrl"),
            "raw_category": next(
                (c["classification"]["description"] for c in it.get("classifications", [])), None),
            "url": f"{BASE}/job/{it['id']}",
            "posted_at": it.get("listingDate"),
        })
    return jobs


def scrape(keyword: str = "", pages: int = 3) -> list[dict]:
    slug = re.sub(r"\s+", "-", keyword.strip().lower())
    path = f"/{slug}-jobs" if slug else "/jobs"
    out = []
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        for page in range(1, pages + 1):
            r = client.get(BASE + path, params={"page": page} if page > 1 else None)
            r.raise_for_status()
            jobs = _parse(r.text)
            if not jobs:
                break
            out += jobs
            time.sleep(1.5)
    return out
