"""Read a user's public GitHub repos and turn them into *evidence* of skills.

Evidence is deterministic (languages, deps, file names, README keywords) so the gap map
never depends on a model hallucinating what the repos contain.
"""
from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests

from .config import USER_AGENT

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
CODE_EXT = (".py", ".js", ".ts", ".java", ".go", ".cpp", ".c", ".rs", ".kt")
SKIP = ("test", "tests", "node_modules", "vendor", "dist", "build", "migrations", "__init__")

# keyword -> skill label. Matched against deps, file paths and README text.
SKILL_KEYWORDS: Dict[str, List[str]] = {
    "REST API design": ["fastapi", "flask", "express", "django", "@app.get", "@app.post", "openapi"],
    "Databases / SQL": ["sqlalchemy", "sqlite", "postgres", "psycopg", "mysql", "alembic", "select * from"],
    "Concurrency / async": ["asyncio", "async def", "threading", "celery", "goroutine", "concurrent.futures"],
    "Testing": ["pytest", "unittest", "jest", "junit", "def test_"],
    "CI/CD & deployment": [".github/workflows", "dockerfile", "docker-compose", "render.yaml", "kubernetes"],
    "Caching / queues": ["redis", "kafka", "rabbitmq", "memcached"],
    "Frontend": ["react", "vue", "jinja2", "tailwind", "<html"],
    "ML / GenAI": ["torch", "transformers", "langchain", "openai", "anthropic", "faiss", "embedding", "rag"],
    "Data structures & algorithms": ["heapq", "bisect", "dijkstra", "segment tree", "binary search", "dp["],
    "System design thinking": ["architecture", "idempotent", "rate limit", "retry", "webhook", "queue"],
}


def _headers() -> Dict[str, str]:
    h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    tok = os.getenv("GITHUB_TOKEN")  # strongly recommended: 60 req/h anonymous vs 5000 authed
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(url: str) -> requests.Response:
    r = requests.get(url, headers=_headers(), timeout=30)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise RuntimeError("GitHub rate limit hit. Set GITHUB_TOKEN to raise the limit.")
    return r


def list_repos(username: str, limit: int = 8) -> List[Dict[str, Any]]:
    r = _get(f"{API}/users/{username}/repos?per_page=100&sort=updated")
    if r.status_code != 200:
        raise RuntimeError(f"Could not list repos for {username}: HTTP {r.status_code}")
    repos = [x for x in r.json() if not x["fork"] and x["size"] > 0]
    return repos[:limit]


def _raw(owner: str, repo: str, branch: str, path: str) -> Optional[str]:
    r = requests.get(f"{RAW}/{owner}/{repo}/{branch}/{path}", headers={"User-Agent": USER_AGENT}, timeout=30)
    return r.text if r.status_code == 200 else None


def repo_tree(owner: str, repo: str, branch: str) -> List[str]:
    r = _get(f"{API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
    if r.status_code != 200:
        return []
    return [t["path"] for t in r.json().get("tree", []) if t["type"] == "blob"]


def pick_code_files(paths: List[str], n: int = 3) -> List[str]:
    """Prefer meaty, central-looking source files: not tests, not tiny, shallow paths first."""
    cands = [p for p in paths if p.endswith(CODE_EXT) and not any(s in p.lower() for s in SKIP)]
    cands.sort(key=lambda p: (p.count("/"), -len(p)))
    return cands[:n]


def analyze_repo(owner: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    name, branch = meta["name"], meta.get("default_branch", "main")
    paths = repo_tree(owner, name, branch)
    readme = _raw(owner, name, branch, "README.md") or ""
    deps = "\n".join(filter(None, (_raw(owner, name, branch, f) for f in
                                   ("requirements.txt", "package.json", "pyproject.toml", "go.mod"))))
    haystack = "\n".join([readme, deps, "\n".join(paths)]).lower()
    files = {p: _raw(owner, name, branch, p) or "" for p in pick_code_files(paths)}
    haystack += "\n".join(files.values()).lower()
    skills = {}
    for skill, kws in SKILL_KEYWORDS.items():
        hits = sorted({k for k in kws if k in haystack})
        if hits:
            skills[skill] = hits
    return {
        "name": name, "url": meta["html_url"], "language": meta.get("language"),
        "description": meta.get("description"), "readme_excerpt": re.sub(r"\s+", " ", readme)[:600],
        "skills": skills, "files": files,
    }


_CACHE: Dict[str, Any] = {}
CACHE_TTL = 600  # seconds; avoids re-hitting GitHub on every page refresh


def analyze_user(username: str, limit: int = 6) -> List[Dict[str, Any]]:
    key = f"{username.lower()}:{limit}"
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    metas = list_repos(username, limit)
    # Repos are independent, so fetch them in parallel instead of one after another.
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(lambda m: analyze_repo(username, m), metas))
    _CACHE[key] = (time.time(), result)
    return result