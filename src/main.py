"""SlothPrep – web UI + API (Google-first demo)."""

from __future__ import annotations

import re
import tempfile
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Query, HTTPException, Body, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .github_ingest import (
    fetch_company,
    list_companies,
    merge_unique_questions,
    GitHubIngestError,
)
from .config import ATTRIBUTION, DEFAULT_COMPANY
from .llm import summarize_experience, generate_repo_questions, LLMError
from . import llm, repos as repos_mod, repo_questions
from .gap import build_gap_map, build_plan, topic_weights

from fastapi.responses import RedirectResponse

CACHE_DIR = Path(tempfile.gettempdir()) / "slothprep_cache"   # 24h CSV cache, avoids 5 fetches per page
COMPANY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")

# Tiny in-memory rate limiter: protects the GitHub token and the model on a public demo.
_HITS: dict = defaultdict(deque)
RATE_LIMIT, RATE_WINDOW = 30, 60  # requests per window per client


def rate_limit(request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    now = time.time()
    q = _HITS[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Slow down a little (sloths approve). Try again in a minute.")
    q.append(now)


def _company(raw: str) -> str:
    c = raw.lower().strip().replace(" ", "-")
    if not COMPANY_RE.match(c):
        raise HTTPException(status_code=400, detail="Invalid company name.")
    return c


def _fetch(company: str):
    try:
        qset = fetch_company(company, cache_dir=CACHE_DIR)
    except GitHubIngestError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # network errors from requests
        raise HTTPException(status_code=502, detail=f"Could not fetch question lists: {e.__class__.__name__}")
    if not any(qset.windows.values()):
        raise HTTPException(status_code=404, detail=f"No question data found for '{company}'.")
    return qset


# ---------- create app FIRST ----------
app = FastAPI(
    title="SlothPrep",
    description="Interview prep that does the hunting so you don't have to.",
    version="0.2.0",
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ---------- routes ----------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "SlothPrep",
            "attribution": ATTRIBUTION,
            "default_company": DEFAULT_COMPANY,
        },
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "SlothPrep",
        "default_company": DEFAULT_COMPANY,
    }


@app.get("/api/companies")
def api_companies(limit: int = Query(50, ge=1, le=200)):
    try:
        companies = list_companies()
        return {"count": len(companies), "companies": companies[:limit]}
    except GitHubIngestError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/questions/{company}")
def api_questions(
    company: str,
    window: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=100),
):
    qset = _fetch(_company(company))

    if window:
        questions = sorted(
            qset.windows.get(window, []),
            key=lambda q: q.frequency or 0,
            reverse=True,
        )[:top]
        source_label = window
    else:
        questions = merge_unique_questions(qset)[:top]
        source_label = "merged (prefer recent)"

    return {
        "company": qset.company,
        "fetched_at": qset.fetched_at,
        "source_repo": qset.source_repo,
        "window": source_label,
        "count": len(questions),
        "questions": [q.to_dict() for q in questions],
        "summary": {w: len(qs) for w, qs in qset.windows.items()},
        "attribution": qset.attribution,
        "notes": qset.notes,
    }


@app.get("/prep/{company}", response_class=HTMLResponse)
def prep_page(request: Request, company: str):
    try:
        qset = _fetch(_company(company))
        top_questions = merge_unique_questions(qset)[:30]
    except HTTPException as e:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"error": e.detail, "title": "Error"},
            status_code=e.status_code,
        )

    return templates.TemplateResponse(
        request=request,
        name="prep.html",
        context={
            "title": f"SlothPrep – {company.title()}",
            "company": qset.company,
            "questions": top_questions,
            "summary": {w: len(qs) for w, qs in qset.windows.items()},
            "fetched_at": qset.fetched_at,
            "attribution": qset.attribution,
        },
    )


# ----- open-weight model routes (Priority 1 – core of the challenge) -----

@app.post("/api/summarize", dependencies=[Depends(rate_limit)])
def api_summarize(payload: dict = Body(...)):
    """
    Summarize a pasted interview experience with an open-weight model.
    Body: { "text": "...", "company": "google" }
    """
    text = (payload.get("text") or "").strip()
    company = (payload.get("company") or "google").strip()
    if not text or len(text) < 40:
        raise HTTPException(status_code=400, detail="Paste a longer experience text.")
    try:
        summary = summarize_experience(text, company=company)
        return {
            "company": company,
            "summary": summary,
            "model_note": "Generated by local/open-weight model (Ollama or configured open-weight host).",
            "disclaimer": "Self-reported patterns only — not guaranteed interview questions.",
        }
    except LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/repo-questions", dependencies=[Depends(rate_limit)])
def api_repo_questions(payload: dict = Body(...)):
    """
    Generate practice questions about the user's own repo.
    Body: { "repo_name": "...", "repo_summary": "...", "company": "google", "n": 5 }
    """
    repo_name = (payload.get("repo_name") or "my-repo").strip()
    repo_summary = (payload.get("repo_summary") or "").strip()
    company = (payload.get("company") or "google").strip()
    n = max(1, min(int(payload.get("n") or 5), 8))
    if not repo_summary or len(repo_summary) < 40:
        raise HTTPException(
            status_code=400,
            detail="Provide a longer repo summary / README.",
        )
    try:
        questions = generate_repo_questions(
            repo_name, repo_summary, company=company, n=n
        )
        return {
            "repo_name": repo_name,
            "company": company,
            "questions": questions,
            "model_note": "Generated by local/open-weight model.",
            "disclaimer": "Practice questions derived from your repo — not guaranteed interview questions.",
        }
    except LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ---- Priority 1/2: model status, gap map, plan, repo-aware questions -------------------

@app.get("/api/llm/status")
def llm_status():
    return llm.status()


def _load(username: str, limit: int):
    username = username.strip().lstrip("@")
    if not repos_mod.USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Invalid GitHub username.")
    try:
        rs = repos_mod.analyze_user(username, limit)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not rs:
        raise HTTPException(status_code=404, detail=f"No public, non-fork repos found for '{username}'.")
    return rs


@app.get("/api/gap/{company}", dependencies=[Depends(rate_limit)])
def api_gap(company: str, github: str, limit: int = Query(6, ge=1, le=10)):
    rs = _load(github, limit)
    return {"github": github, "repos_scanned": [r["name"] for r in rs], "gap_map": build_gap_map(rs),
            "note": "Deterministic keyword evidence from your repos. 'gap' means no evidence found, not that you lack the skill."}


@app.get("/api/plan/{company}", dependencies=[Depends(rate_limit)])
def api_plan(company: str, github: str, days: int = Query(14, ge=1, le=60),
                   hours: float = Query(2, ge=0.5, le=12), limit: int = Query(6, ge=1, le=10)):
    qset = _fetch(_company(company))
    qs = merge_unique_questions(qset)[:60]
    rs = _load(github, limit)
    gaps = build_gap_map(rs)
    return {"company": qset.company, "github": github, "repos_scanned": [r["name"] for r in rs],
            "top_topics": topic_weights(qs), "gap_map": gaps,
            "plan": build_plan(qs, gaps, days, hours), "attribution": qset.attribution,
            "topic_note": "Topics are inferred from question titles with keywords (crude, not official).",
            "gap_note": "Evidence comes from your public repos only (not LeetCode/Codeforces practice). 'gap' = no evidence found."}


@app.get("/api/code-questions", dependencies=[Depends(rate_limit)])
def api_code_questions(github: str, repo: str, n: int = Query(4, ge=1, le=8)):
    rs = {r["name"]: r for r in _load(github, 10)}
    if repo not in rs:
        raise HTTPException(status_code=404, detail="Repo not found among scanned repos")
    try:
        return {"repo": repo, "model": llm.MODEL, "files_used": list(rs[repo]["files"]),
                "questions": repo_questions.generate(rs[repo], n)}
    except llm.LLMUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/check-answer", dependencies=[Depends(rate_limit)])
def api_check_answer(payload: dict = Body(...)):
    """Body: {"github": "...", "repo": "...", "question": "...", "answer": "..."}"""
    github, repo = (payload.get("github") or ""), (payload.get("repo") or "")
    question, answer = (payload.get("question") or "").strip(), (payload.get("answer") or "").strip()
    if not question or len(answer) < 10 or len(answer) > 4000:
        raise HTTPException(status_code=400, detail="Provide a question and an answer (10-4000 characters).")
    rs = {r["name"]: r for r in _load(github, 10)}
    if repo not in rs:
        raise HTTPException(status_code=404, detail="Repo not found among scanned repos")
    try:
        return {"model": llm.MODEL, "result": repo_questions.check_answer(rs[repo], question, answer)}
    except llm.LLMUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse("/static/favicon.svg")