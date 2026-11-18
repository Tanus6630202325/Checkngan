"""แต่ละเว็บมี module ของตัวเอง และต้องมีฟังก์ชัน scrape(keyword, pages) -> list[dict]
dict แต่ละรายการมี key: source, job_id, title, company, location, salary, job_type, url, posted_at
"""
from . import jobsdb, jobthai, jobtopgun

SCRAPERS = {
    "jobthai": jobthai.scrape,
    "jobsdb": jobsdb.scrape,
    "jobtopgun": jobtopgun.scrape,
}
