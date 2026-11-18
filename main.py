from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import db
import matcher
from scrapers import SCRAPERS

app = FastAPI(title="CheckNgan")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/api/jobs")
def jobs(q: str = "", source: str = "", location: str = "", category: str = "",
         limit: int = Query(30, le=100), offset: int = 0):
    total, rows = db.search_jobs(q, source, location, category, limit, offset)
    return {"total": total, "jobs": rows}


@app.get("/api/categories")
def categories(source: str = ""):
    return db.categories(source)


@app.get("/api/sources")
def sources():
    return db.sources()


@app.post("/api/match")
async def match(file: UploadFile = File(...), location: str = Form("")):
    data = await file.read()
    try:
        # เรียก API แบบ blocking จึงรันใน thread pool ไม่ให้ค้าง server
        return await run_in_threadpool(matcher.match_resume, file.filename or "", data, location.strip())
    except matcher.MatchError as e:
        raise HTTPException(400, str(e))


def _run(keyword: str, pages: int):
    for fn in SCRAPERS.values():
        try:
            db.upsert_jobs(fn(keyword, pages))
        except Exception as e:
            print("scrape failed:", e)


@app.post("/api/scrape")
def scrape(background: BackgroundTasks, keyword: str = "", pages: int = Query(3, le=10)):
    background.add_task(_run, keyword, pages)
    return {"status": "started"}
