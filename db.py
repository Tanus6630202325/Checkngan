import sqlite3
from pathlib import Path

from categories import categorize

DB_PATH = Path(__file__).parent / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    source     TEXT NOT NULL,
    job_id     TEXT NOT NULL,
    title      TEXT NOT NULL,
    company    TEXT,
    location   TEXT,
    salary     TEXT,
    job_type   TEXT,
    url        TEXT NOT NULL,
    posted_at  TEXT,
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, job_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_at DESC);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn):
    """เพิ่มคอลัมน์ category ให้ฐานข้อมูลเดิม แล้วจัดหมวดย้อนหลังให้งานที่มีอยู่"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "logo" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN logo TEXT")
    if "category" in cols:
        return
    conn.execute("ALTER TABLE jobs ADD COLUMN category TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category)")
    rows = conn.execute("SELECT source, job_id, title, job_type FROM jobs").fetchall()
    conn.executemany(
        "UPDATE jobs SET category=? WHERE source=? AND job_id=?",
        [
            # JobThai เก็บหมวดงานไว้ใน job_type อยู่แล้ว เว็บอื่นเดาจากชื่อตำแหน่ง
            (categorize(r["job_type"] if r["source"] == "jobthai" else None, r["title"]),
             r["source"], r["job_id"])
            for r in rows
        ],
    )
    conn.commit()


def upsert_jobs(jobs: list[dict]) -> int:
    rows = [
        {**j, "category": categorize(j.get("raw_category"), j["title"]), "logo": j.get("logo")}
        for j in jobs
    ]
    with connect() as conn:
        conn.executemany(
            """INSERT INTO jobs (source, job_id, title, company, location, salary, job_type, url, posted_at, category, logo)
               VALUES (:source, :job_id, :title, :company, :location, :salary, :job_type, :url, :posted_at, :category, :logo)
               ON CONFLICT(source, job_id) DO UPDATE SET
                 title=excluded.title, company=excluded.company, location=excluded.location,
                 salary=excluded.salary, job_type=excluded.job_type, url=excluded.url,
                 posted_at=excluded.posted_at, category=excluded.category,
                 logo=COALESCE(excluded.logo, jobs.logo),
                 scraped_at=CURRENT_TIMESTAMP""",
            rows,
        )
    return len(jobs)


def categories(source=""):
    with connect() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS n FROM jobs WHERE (?='' OR source=?) GROUP BY category ORDER BY n DESC",
            (source, source),
        ).fetchall()
    return [{"category": r["category"], "count": r["n"]} for r in rows if r["category"]]


def candidate_jobs(categories, keywords, locations=(), limit=80):
    """งานที่น่าจะเข้ากับโปรไฟล์: อยู่ในหมวดที่เหมาะ หรือชื่อตำแหน่งมีคำสำคัญ (เรียงงานตรงสถานที่ก่อน)"""
    conds, args = [], []
    if categories:
        conds.append(f"category IN ({','.join('?' * len(categories))})")
        args += list(categories)
    for kw in keywords:
        conds.append("title LIKE ?")
        args.append(f"%{kw}%")
    if not conds:
        return []
    loc_score, loc_args = "0", []
    if locations:
        loc_score = "(" + " OR ".join("location LIKE ?" for _ in locations) + ")"
        loc_args = [f"%{x}%" for x in locations]
    with connect() as conn:
        rows = conn.execute(
            f"""SELECT * FROM jobs WHERE {' OR '.join(conds)}
                ORDER BY {loc_score} DESC, COALESCE(posted_at, scraped_at) DESC LIMIT ?""",
            args + loc_args + [limit],  # ลำดับต้องตรงกับ ? ใน SQL: WHERE ก่อน แล้วค่อย ORDER BY
        ).fetchall()
    return [dict(r) for r in rows]


def search_jobs(q="", source="", location="", category="", limit=50, offset=0):
    where, args = [], []
    if category:
        where.append("category = ?")
        args.append(category)
    if q:
        where.append("(title LIKE ? OR company LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    if source:
        where.append("source = ?")
        args.append(source)
    if location:
        where.append("location LIKE ?")
        args.append(f"%{location}%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM jobs {clause}", args).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM jobs {clause} ORDER BY COALESCE(posted_at, scraped_at) DESC LIMIT ? OFFSET ?",
            args + [limit, offset],
        ).fetchall()
    return total, [dict(r) for r in rows]


def sources():
    with connect() as conn:
        rows = conn.execute(
            "SELECT source, COUNT(*) AS n FROM jobs GROUP BY source ORDER BY n DESC"
        ).fetchall()
        return [{"source": r["source"], "count": r["n"]} for r in rows]
