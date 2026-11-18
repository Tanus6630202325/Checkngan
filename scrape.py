"""รัน: python scrape.py [keyword] [pages]"""
import sys

import db
from scrapers import SCRAPERS

if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    for name, fn in SCRAPERS.items():
        try:
            jobs = fn(keyword, pages)
            print(f"{name}: {db.upsert_jobs(jobs)} jobs")
        except Exception as e:
            print(f"{name}: FAILED - {e}")
