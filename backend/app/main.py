import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import config, nlp, rag
from .retriever import get_index

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rsa")

app = FastAPI(title="Rural Scheme Advisor API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_hits: dict[str, deque] = defaultdict(deque)


def check_rate_limit(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "Too many requests. Please wait a minute.")
    q.append(now)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=config.MAX_QUESTION_CHARS)
    session_id: str = Field(default="default", min_length=1, max_length=64)
    language: str | None = Field(default=None, description="en | hi | or. Omit to auto-detect.")


class Source(BaseModel):
    id: int
    scheme: str
    document: str
    page: int
    section: str | None = None
    source_url: str | None = None
    score: float


class ChatResponse(BaseModel):
    answer: str
    status: str  # answered | not_found | error
    language: str
    scheme_id: str | None
    intent: str
    sources: list[Source]
    follow_ups: list[str]


class RecommendRequest(BaseModel):
    needs: list[str] = Field(default_factory=list, max_length=10)
    occupation: str | None = Field(default=None, max_length=40)
    state: str | None = Field(default=None, max_length=60)


@app.get("/health")
def health():
    idx = get_index()
    return {"status": "ok", "index_loaded": idx is not None, "chunks": len(idx.chunks) if idx else 0}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    check_rate_limit(request)
    try:
        return rag.answer_question(req.question.strip(), req.session_id, req.language)
    except Exception:
        log.exception("chat failed")  # details go to logs, never to the user
        raise HTTPException(503, "The assistant is temporarily unavailable. Please try again.")


@app.get("/api/schemes")
def list_schemes():
    return [{k: s[k] for k in ("id", "name", "full_name", "category", "summary", "official_url")} for s in nlp.load_schemes()]


@app.get("/api/categories")
def categories():
    return sorted({s["category"] for s in nlp.load_schemes()})


@app.get("/api/schemes/{scheme_id}")
def scheme_detail(scheme_id: str):
    s = nlp.get_scheme(scheme_id)
    if not s:
        raise HTTPException(404, "Scheme not found")
    return s


@app.post("/api/recommendations")
def recommendations(req: RecommendRequest):
    return {
        "disclaimer": "These are suggestions to explore, not an eligibility decision. Check official criteria.",
        "results": nlp.recommend(req.needs, req.occupation),
    }
