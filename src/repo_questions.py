"""Questions about YOUR code, generated and checked by the open-weight model."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import llm

GEN_SYSTEM = (
    "You are a strict but fair software interviewer. You are given real code from a candidate's "
    "own GitHub project. Ask questions an interviewer would ask about THIS code: design trade-offs, "
    "failure modes, scaling, and edge cases. Every question must cite the file it is about. "
    'Return ONLY JSON: [{"file": str, "question": str, "why_asked": str}]'
)

CHECK_SYSTEM = (
    "You grade a candidate's answer about their own code. Use ONLY the code provided as ground truth. "
    "If the answer claims something the code does not do, say so. "
    'Return ONLY JSON: {"verdict": "correct"|"partial"|"incorrect", '
    '"matches_code": [str], "contradicts_code": [str], "missing": [str]}'
)


def _code_block(repo: Dict[str, Any], max_chars: int = 4500) -> Tuple[str, List[str]]:
    """Return (prompt text, paths actually shown). The budget is split across files so one long
    file cannot crowd out the rest."""
    files = {p: t for p, t in repo["files"].items() if t}
    if not files:
        return "", []
    per_file = max_chars // len(files)
    parts, shown = [], []
    for path, text in files.items():
        parts.append(f"### {path}\n{text[:per_file]}")
        shown.append(path)
    return "\n\n".join(parts), shown


def generate(repo: Dict[str, Any], n: int = 4) -> List[Dict[str, str]]:
    code, shown = _code_block(repo)
    if not shown:
        raise llm.LLMUnavailable("No readable source files found in this repo.")
    user = f"Project: {repo['name']}\nREADME: {repo['readme_excerpt']}\n\n{code}\n\nAsk {n} questions."
    out = llm.chat_json(GEN_SYSTEM, user)
    if not isinstance(out, list):
        raise llm.LLMUnavailable("Model returned the wrong JSON shape; try again or use a larger model.")
    valid = set(shown)
    # Drop questions pointing at files the model was never shown: cheap hallucination guard.
    return [q for q in out if isinstance(q, dict) and q.get("file") in valid and q.get("question")]


def check_answer(repo: Dict[str, Any], question: str, answer: str) -> Dict[str, Any]:
    code, _ = _code_block(repo)
    user = f"Question: {question}\n\nCandidate answer: {answer}\n\nCode:\n{code}"
    return llm.chat_json(CHECK_SYSTEM, user)
