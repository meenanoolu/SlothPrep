"""SlothPrep – web UI + API (Google-first demo)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Query, HTTPException
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

app = FastAPI(
    title="SlothPrep",
    description="Interview prep that does the hunting so you don't have to.",
    version="0.1.0",
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

static_dir = BASE_DIR.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
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
async def health():
    return {"status": "ok", "service": "SlothPrep", "default_company": DEFAULT_COMPANY}


@app.get("/api/companies")
async def api_companies(limit: int = Query(50, ge=1, le=200)):
    try:
        companies = list_companies()
        return {"count": len(companies), "companies": companies[:limit]}
    except GitHubIngestError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/questions/{company}")
async def api_questions(
    company: str,
    window: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=100),
):
    try:
        qset = fetch_company(company.lower().strip())
    except GitHubIngestError as e:
        raise HTTPException(status_code=502, detail=str(e))

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
async def prep_page(request: Request, company: str):
    try:
        qset = fetch_company(company.lower().strip())
        top_questions = merge_unique_questions(qset)[:30]
    except GitHubIngestError as e:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"error": str(e), "title": "Error"},
            status_code=502,
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