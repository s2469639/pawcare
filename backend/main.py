"""PawCare FastAPI 앱. 실행: uvicorn backend.main:app --reload"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import re

from fastapi.responses import FileResponse

from .database import ROOT, connect, init_db, upload_dir
from .routes import ai, dogs, misc, records, routine, tasks
from .seed import seed


def load_env() -> None:
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_env()
    conn = connect()
    try:
        init_db(conn)
        if conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 0:
            seed(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="PawCare", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        field = ".".join(str(x) for x in e["loc"] if x not in ("body", "query", "path"))
        msgs.append({"field": field, "message": e["msg"].removeprefix("Value error, ")})
    return JSONResponse(status_code=422, content={"detail": "입력값을 확인해 주세요.", "errors": msgs})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})


@app.get("/api/health")
def health():
    return {"ok": True, "ai_configured": bool(os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_MODEL"))}


for r in (misc.router, dogs.router, records.router, tasks.router, ai.router, routine.router):
    app.include_router(r)

_FILE = re.compile(r"^[A-Za-z0-9._-]+\.(webp|jpg|png)$")
_MEDIA = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png"}


@app.get("/uploads/dogs/{filename}")
def uploaded_photo(filename: str):
    """업로드된 반려견 사진. 파일명은 무작위이며 경로 이동 문자는 허용하지 않는다."""
    if not _FILE.match(filename) or ".." in filename:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    path = upload_dir() / "dogs" / filename
    if not path.is_file():
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    return FileResponse(path, media_type=_MEDIA[filename.rsplit(".", 1)[1]],
                        headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})

app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
