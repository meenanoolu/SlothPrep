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

USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")  # GitHub username rules
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
CODE_EXT = (".py", ".js", ".ts", ".java", ".go", ".cpp", ".c", ".rs", ".kt")
# Matched against whole path segments / file stems, not substrings ("distance.py" is fine).
SKIP_PARTS = {"test", "tests", "node_modules", "vendor", "dist", "build", "migrations", "__init__", "docs", "examples"}
ENTRY_NAMES = {"main", "app", "server", "index", "core", "api", "service", "models", "handler"}

# keyword -> skill label. Matched against deps, file paths and README text.
SKILL_KEYWORDS: Dict[str, List[str]] = {
    "REST API design": ["fastapi", "flask", "express", "django", "@app.get", "@app.post", "openapi"],
    "Databases / SQL": ["sqlalchemy", "sqlite", "postgres", "psycopg", "mysql", "alembic", "select * from"],
    "Concurrency / async": ["asyncio", "async def", "threading", "celery", "goroutine", "concurrent.futures"],
    "Testing": ["pytest", "unittest", "jest", "junit", "def test_", "tests/", "test_"],
    "CI/CD & deployment": [".github/workflows", "dockerfile", "docker-compose", "render.yaml", "kubernetes"],
    "Caching / queues": ["redis", "kafka", "rabbitmq", "memcached"],
    "Frontend": ["react", "vue", "jinja2", "tailwind", "<html"],
    "ML / GenAI": ["torch", "transformers", "langchain", "openai", "anthropic", "faiss", "embedding", "rag"],
    "Data structures & algorithms": ["heapq", "bisect", "dijkstra", "segment tree", "binary search", "dp["],
    "System design thinking": ["architecture", "idempotent", "rate limit", "retry", "webhook", "queue"],
}


def _has(keyword: str, text: str) -> bool:
    """Whole-token match so 'rag' does not hit 'storage' and 'react' does not hit 'reaction'."""
    pre = r"(?<![a-z0-9_])" if keyword[0].isalnum() else ""
    post = r"(?![a-z0-9_])" if keyword[-1].isalnum() else ""
    return re.search(pre + re.escape(keyword) + post, text) is not None


def _headers() -> Dict[str, str]:
    h = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    tok = os.getenv("GITHUB_TOKEN")  # strongly recommended: 60 req/h anonymous vs 5000 authed
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _get(url: str) -> requests.Response:
    try:
        r = requests.get(url, headers=_headers(), timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach GitHub: {e.__class__.__name__}") from e
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise RuntimeError("GitHub rate limit hit. Set GITHUB_TOKEN to raise the limit.")
    return r


def list_repos(username: str, limit: int = 8) -> List[Dict[str, Any]]:
    if not USERNAME_RE.match(username or ""):
        raise RuntimeError("Invalid GitHub username.")
    r = _get(f"{API}/users/{username}/repos?per_page=100&sort=updated")
    if r.status_code != 200:
        raise RuntimeError(f"Could not list repos for {username}: HTTP {r.status_code}")
    repos = [x for x in r.json() if not x["fork"] and x["size"] > 0]
    return repos[:limit]


def _raw(owner: str, repo: str, branch: str, path: str) -> Optional[str]:
    try:
        r = requests.get(f"{RAW}/{owner}/{repo}/{branch}/{path}", headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException:
        return None
    return r.text if r.status_code == 200 else None


def repo_tree(owner: str, repo: str, branch: str) -> Dict[str, int]:
    """path -> size in bytes for every file in the repo."""
    r = _get(f"{API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
    if r.status_code != 200:
        return {}
    return {t["path"]: t.get("size", 0) for t in r.json().get("tree", []) if t["type"] == "blob"}


def _skipped(path: str) -> bool:
    parts = [p.lower() for p in path.split("/")]
    stem = parts[-1].rsplit(".", 1)[0]
    if stem.startswith("test_") or stem.endswith("_test"):
        return True
    return any(p in SKIP_PARTS for p in parts[:-1]) or stem in SKIP_PARTS


def pick_code_files(tree: Dict[str, int], n: int = 3) -> List[str]:
    """Prefer central source files: entry-point names first, then bigger files, then shallow paths.
    Tiny files (<400 bytes) and files over 60 KB are skipped; they make poor interview material."""
    cands = [p for p, size in tree.items()
             if p.endswith(CODE_EXT) and not _skipped(p) and 400 <= size <= 60_000]

    def score(p: str):
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        return (stem not in ENTRY_NAMES, p.count("/"), -tree[p])

    return sorted(cands, key=score)[:n]


def analyze_repo(owner: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    name, branch = meta["name"], meta.get("default_branch", "main")
    tree = repo_tree(owner, name, branch)
    paths = list(tree)
    readme = _raw(owner, name, branch, "README.md") or ""
    deps = "\n".join(filter(None, (_raw(owner, name, branch, f) for f in
                                   ("requirements.txt", "package.json", "pyproject.toml", "go.mod"))))
    haystack = "\n".join([readme, deps, "\n".join(paths)]).lower()
    files = {p: _raw(owner, name, branch, p) or "" for p in pick_code_files(tree)}
    haystack += "\n" + "\n".join(files.values()).lower()
    skills = {}
    for skill, kws in SKILL_KEYWORDS.items():
        hits = sorted({k for k in kws if _has(k, haystack)})
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