"""PawCare FastAPI 앱. 실행: uvicorn backend.main:app --reload"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import re
import sqlite3

from fastapi.responses import FileResponse

from .database import ROOT, connect, get_db, init_db, upload_dir
from . import auth as auth_lib
from .deps import FieldError, current_account
from .routes import ai, auth, dogs, invites, media, misc, records, routine, tasks
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
        if not auth_lib.demo_mode() and conn.execute("SELECT 1 FROM accounts WHERE is_demo=1").fetchone():
            logging.getLogger("uvicorn.error").warning(
                "데모 계정이 있습니다(공개 비밀번호). 인터넷에 공개하기 전에 데모 계정을 삭제하세요. 로컬 시연은 .env의 DEMO_MODE=1을 사용하세요.")
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


@app.exception_handler(FieldError)
async def field_error_handler(request: Request, exc: FieldError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message, "errors": [{"field": exc.field, "message": exc.message}]})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."})


@app.get("/api/health")
def health():
    return {"ok": True, "demo_mode": auth_lib.demo_mode(),
            "ai_configured": bool(os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_MODEL"))}


for r in (auth.router, invites.router, misc.router, dogs.router, media.router, records.router, tasks.router, ai.router, routine.router):
    app.include_router(r)

_FILE = re.compile(r"^[A-Za-z0-9._-]+\.(webp|jpg|png)$")
_MEDIA = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png"}


@app.get("/uploads/dogs/{filename}")
def uploaded_photo(filename: str, account: dict = Depends(current_account), db: sqlite3.Connection = Depends(get_db)):
    """반려견 프로필 사진. 로그인한 사람 중 같은 유치원 직원 또는 그 아이의 보호자만 볼 수 있다.
    권한이 없으면 파일이 있는지 알 수 없도록 404로 답한다. 파일명은 무작위이며 경로 이동 문자는 허용하지 않는다."""
    m = _FILE.match(filename)
    if not m or ".." in filename:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    dog_id = int(filename.split("-", 1)[0]) if filename.split("-", 1)[0].isdigit() else None
    dog = db.execute("SELECT org_id FROM dogs WHERE id=?", (dog_id,)).fetchone() if dog_id else None
    if dog is None:
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    if account["role"] == "staff":
        allowed = dog["org_id"] == account["org_id"]
    else:
        allowed = db.execute("SELECT 1 FROM guardian_dogs WHERE account_id=? AND dog_id=?", (account["id"], dog_id)).fetchone() is not None
    path = upload_dir() / "dogs" / filename
    if not allowed or not path.is_file():
        raise HTTPException(404, "사진을 찾을 수 없습니다.")
    return FileResponse(path, media_type=_MEDIA[filename.rsplit(".", 1)[1]],
                        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
