"""
Open-weight model interface for SlothPrep.

Primary path: Ollama (local, private, free after download).
Optional fallback: any OpenAI-compatible endpoint that serves open weights
(Groq, Together, Fireworks, etc.).

This module is the core of the "open-source AI at its core" claim.
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from typing import Optional

# ---------------------------------------------------------------------------
# Config – prefer local Ollama
# ---------------------------------------------------------------------------
OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "gemma3:4b"

# Any OpenAI-compatible endpoint serving open weights. Ollama itself exposes one at
# http://localhost:11434/v1, so LLM_BASE_URL works for local Ollama too (no key needed).
# Legacy names OPENAI_BASE / OPENAI_API_KEY / OPENAI_MODEL are still accepted.
OPENAI_BASE = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE", "")
OPENAI_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "llama-3.1-8b-instant"


class LLMError(Exception):
    pass


def _ollama_generate(prompt: str, system: Optional[str] = None) -> str:
    url = f"{OLLAMA_BASE}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 8192},  # default context is small; avoid silent truncation
    }
    if system:
        payload["system"] = system

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return (body.get("response") or "").strip()
    except urllib.error.URLError as e:
        raise LLMError(
            f"Ollama not reachable at {OLLAMA_BASE}. "
            f"Is Ollama running? ({e})"
        ) from e


def _openai_compatible_generate(prompt: str, system: Optional[str] = None) -> str:
    if not OPENAI_BASE:
        raise LLMError("LLM_BASE_URL not set")

    url = f"{OPENAI_BASE.rstrip('/')}/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise LLMError(f"OpenAI-compatible endpoint failed: {e}") from e


def generate(prompt: str, system: Optional[str] = None) -> str:
    """
    Main entry point. If LLM_BASE_URL is set, use that open-weight endpoint
    (hosted, or Ollama's /v1). Otherwise try local Ollama.
    """
    if OPENAI_BASE:
        return _openai_compatible_generate(prompt, system=system)
    try:
        return _ollama_generate(prompt, system=system)
    except LLMError as e:
        raise LLMError(
            "No open-weight model available. Start Ollama (`ollama serve` + "
            f"`ollama pull {OLLAMA_MODEL}`) or set LLM_BASE_URL (+ LLM_MODEL, LLM_API_KEY)."
        ) from e


# ---------------------------------------------------------------------------
# Task-specific helpers (the actual "does the work for you" features)
# ---------------------------------------------------------------------------

SUMMARIZE_SYSTEM = """You are helping a candidate prepare for interviews.
Summarize the interview experience in clear, structured markdown.
Use only information present in the text. Do not invent questions or rounds.
Always remind the reader these are self-reported patterns, not guarantees.
Keep it concise."""

def summarize_experience(raw_text: str, company: str = "Google") -> str:
    prompt = f"""Summarize this {company} interview experience post.

Return markdown with these sections if the information exists:
- Role / Level
- Stages / Rounds
- Topics & question patterns mentioned
- What candidates found hard
- Common mistakes or tips
- Overall signal (and a one-line confidence note)

Text:
\"\"\"
{raw_text[:12000]}
\"\"\"
"""
    return generate(prompt, system=SUMMARIZE_SYSTEM)


REPO_QUESTIONS_SYSTEM = """You generate realistic technical interview questions
about a candidate's own projects. Questions must be answerable from the provided
repo description/code summary only. Prefer depth over trick questions.
Label them as practice questions, not guaranteed interview questions."""

def generate_repo_questions(
    repo_name: str,
    repo_summary: str,
    company: str = "Google",
    n: int = 5,
) -> str:
    prompt = f"""Generate {n} technical interview-style questions about this repository.
Company focus: {company}.
Repo: {repo_name}

Repo summary / README / key points:
\"\"\"
{repo_summary[:8000]}
\"\"\"

For each question include:
- The question
- Why it is relevant to this repo
- What a strong answer should cover (brief)
"""
    return generate(prompt, system=REPO_QUESTIONS_SYSTEM)

# ---------------------------------------------------------------------------
# Added for gap map / repo-aware questions: status check + JSON helper
# ---------------------------------------------------------------------------
import re

MODEL = OPENAI_MODEL if OPENAI_BASE else OLLAMA_MODEL  # name shown in API responses
LLMUnavailable = LLMError       # alias used by repo_questions.py / main.py


def status() -> dict:
    """Cheap health check so the UI can say honestly whether a model is attached."""
    if OPENAI_BASE:
        try:
            req = urllib.request.Request(f"{OPENAI_BASE.rstrip('/')}/models")
            if OPENAI_API_KEY:
                req.add_header("Authorization", f"Bearer {OPENAI_API_KEY}")
            with urllib.request.urlopen(req, timeout=4) as r:
                return {"available": r.status == 200, "backend": "open-weight endpoint", "model": MODEL}
        except Exception:
            return {"available": False, "backend": "open-weight endpoint (unreachable)", "model": MODEL}
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3) as r:
            return {"available": r.status == 200, "backend": "ollama", "model": OLLAMA_MODEL}
    except Exception:
        return {"available": False, "backend": None, "model": OLLAMA_MODEL}


def extract_json(text: str):
    """Small models wrap JSON in prose/fences. Pull out the first valid JSON value."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("No JSON found in model output")


def chat_json(system: str, user: str, retries: int = 1):
    prompt = user
    for _ in range(retries + 1):
        out = generate(prompt, system=system)
        try:
            return extract_json(out)
        except ValueError:
            prompt = user + "\n\nReturn ONLY valid JSON, nothing else."
    raise LLMError("Model did not return valid JSON")