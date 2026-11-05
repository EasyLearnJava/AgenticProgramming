"""Thin HTTP routes: validate input, call the service, return clear errors."""

import json
import logging
import re
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from policylens.config import load_settings
from policylens import __version__
from policylens.diagnostics import log_exception
from policylens.evaluation import EvaluationJobs
from policylens.ingestion.loaders import load_file
from policylens.service import PolicyService
from policylens.middleware import RequestBodyLimitMiddleware, SafeErrorsMiddleware

logger = logging.getLogger("policylens")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1500)
    source_ids: list[str] = Field(default_factory=list, max_length=50)


def create_app(service=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        # Loading the saved index never triggers paid API calls on startup.
        app.state.service = service or PolicyService(load_settings())
        app.state.jobs = EvaluationJobs(app.state.service)
        yield

    app = FastAPI(title="PolicyLens API", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        # Prevent an unrelated website from submitting files to this local app.
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "DELETE", "PATCH"} and origin:
            parsed = urlparse(origin)
            if parsed.netloc != request.headers.get("host") or parsed.scheme not in {"http", "https"}:
                return JSONResponse({"detail": "Use the local PolicyLens page for this action."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValueError)
    async def invalid_input(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": "PolicyLens", "version": __version__}

    @app.get("/api/status")
    def status(request: Request):
        return request.app.state.service.status()

    @app.post("/api/index")
    def rebuild(request: Request):
        return request.app.state.service.rebuild()

    @app.post("/api/ask")
    def ask(body: AskRequest, request: Request):
        question = body.question.strip()
        if len(question) < 3:
            raise ValueError("Please enter a question with at least three characters.")
        return request.app.state.service.ask(question, body.source_ids)

    @app.post("/api/documents")
    def upload(request: Request, file: UploadFile = File(...)):
        content = file.file.read(10 * 1024 * 1024 + 1)
        return request.app.state.service.upload(file.filename or "document.txt", content)

    @app.get("/api/documents/removed")
    def removed(request: Request):
        return request.app.state.service.uploads.removed()

    @app.delete("/api/documents/{source_id}")
    def remove(source_id: str, request: Request):
        return request.app.state.service.remove_document(source_id)

    @app.post("/api/documents/{source_id}/restore")
    def restore(source_id: str, request: Request):
        return request.app.state.service.restore_document(source_id)

    @app.get("/api/documents/{source_id}")
    def document(source_id: str, request: Request):
        svc = request.app.state.service
        doc = next((doc for doc in svc.documents() if doc["source_id"] == source_id), None)
        if not doc:
            raise HTTPException(404, "Document not found.")
        text = "\n\n".join(part.page_content for part in load_file(doc["path"], doc))
        return {"source_id": source_id, "title": doc["title"], "text": text,
                "url": doc.get("url"), "fetched_at": doc["fetched_at"]}

    @app.post("/api/evaluations")
    def evaluate(request: Request):
        return request.app.state.jobs.start()

    @app.get("/api/evaluations/latest")
    def latest(request: Request):
        folder = request.app.state.service.settings.root / "reports" / "runs"
        files = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return json.loads(files[0].read_text(encoding="utf-8")) if files else None

    @app.get("/api/evaluations/{run_id}")
    def evaluation(run_id: str, request: Request):
        job = request.app.state.jobs.get(run_id)
        if job is None:
            raise HTTPException(404, "Evaluation job not found.")
        return job

    @app.get("/api/reports/{filename}")
    def download_report(filename: str, request: Request):
        if not re.fullmatch(r"[a-f0-9]{32}\.(json|md)", filename):
            raise HTTPException(404, "Report not found.")
        path = request.app.state.service.settings.root / "reports" / "runs" / filename
        if not path.is_file():
            raise HTTPException(404, "Report not found.")
        return FileResponse(path, filename=f"PolicyLens-{filename}")

    from policylens.config import ROOT
    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")

    @app.get("/")
    def home():
        return FileResponse(ROOT / "web" / "index.html")

    # Register Host validation outermost, before reading an untrusted body.
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(SafeErrorsMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"], www_redirect=False)
    return app

