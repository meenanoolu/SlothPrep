"""Gap map (role requirements vs what repos actually prove) and the time-boxed plan.

Both are deterministic on purpose: they must be explainable and reproducible, and they
should still work when no model is attached.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

# Starter profile for the Google-first demo. Weights = how much the role leans on it (1-3).
# These are our own assumptions from public job descriptions, not official Google data.
ROLE_PROFILES: Dict[str, Dict[str, int]] = {
    "google-swe": {
        "Data structures & algorithms": 3,
        "System design thinking": 2,
        "REST API design": 2,
        "Databases / SQL": 2,
        "Testing": 2,
        "Concurrency / async": 1,
        "CI/CD & deployment": 1,
        "Caching / queues": 1,
        "Frontend": 1,
    }
}


def build_gap_map(repos: List[Dict[str, Any]], role: str = "google-swe") -> List[Dict[str, Any]]:
    profile = ROLE_PROFILES.get(role, ROLE_PROFILES["google-swe"])
    rows = []
    for skill, weight in profile.items():
        proof = [{"repo": r["name"], "signals": r["skills"][skill]} for r in repos if skill in r["skills"]]
        status = "proven" if len(proof) >= 2 else "thin" if proof else "gap"
        rows.append({"skill": skill, "weight": weight, "status": status, "evidence": proof})
    order = {"gap": 0, "thin": 1, "proven": 2}
    return sorted(rows, key=lambda r: (order[r["status"]], -r["weight"]))


# The source CSVs have no topic column, so topics are INFERRED from titles with keywords.
# Crude on purpose and labeled as such in the UI; the local model can refine it later.
TITLE_TOPICS: Dict[str, List[str]] = {
    "Arrays & hashing": ["two sum", "array", "duplicate", "product of", "subarray", "anagram", "group"],
    "Strings": ["string", "palindrome", "substring", "parenthes", "word", "character"],
    "Two pointers / sliding window": ["window", "container", "trapping", "longest substring", "sum ii"],
    "Binary search": ["search", "sorted", "rotated", "median", "kth", "peak"],
    "Linked lists": ["linked list", "list node", "cycle", "reorder"],
    "Trees & BST": ["tree", "bst", "ancestor", "traversal", "serialize"],
    "Graphs / BFS / DFS": ["graph", "island", "course", "path", "ladder", "clone", "network", "rotting"],
    "Dynamic programming": ["climb", "coin", "subsequence", "knapsack", "edit distance", "robber", "partition", "unique paths"],
    "Heaps / intervals / greedy": ["interval", "meeting", "merge", "k closest", "top k", "stream", "jump", "schedule"],
    "Design / data structures": ["lru", "design", "iterator", "trie", "implement", "cache", "randomized"],
    "Backtracking": ["permutation", "combination", "subsets", "n-queens", "generate", "sudoku"],
}


def infer_topics(title: str) -> List[str]:
    t = title.lower()
    return [topic for topic, kws in TITLE_TOPICS.items() if any(k in t for k in kws)]


def topic_weights(questions: List[Any], top: int = 8) -> List[tuple]:
    c: Counter = Counter()
    for q in questions:
        for t in (q.topics or infer_topics(q.title)):
            c[t] += (q.frequency or 1.0)
    return [(t, round(w, 1)) for t, w in c.most_common(top)]


def build_plan(questions: List[Any], gaps: List[Dict[str, Any]], days: int, hours_per_day: float) -> List[Dict[str, Any]]:
    """Split total hours across: question-pattern topics, gap skills, repo defense, mock review."""
    days = max(1, min(days, 60))
    total = days * hours_per_day
    topics = topic_weights(questions)
    weak = [g for g in gaps if g["status"] in ("gap", "thin")][:4]

    # tasks: (label, kind, weight)
    tasks = [(f"Practice: {t}", "patterns", w) for t, w in topics]
    tasks += [(f"Close gap: {g['skill']} ({g['status']})", "gap", g["weight"] * 40) for g in weak]
    tasks += [("Defend your own repos (answer repo-specific questions)", "repos", 60)]
    tasks += [("Mock interview + review mistakes", "mock", 50)]
    wsum = sum(w for *_, w in tasks) or 1

    # Snap each task to 30 min (rounding down), then trim the biggest practice blocks until
    # everything fits, so the mock interview at the end is never the thing that gets cut.
    alloc = [max(0.5, int(total * w / wsum * 2) / 2) for *_, w in tasks]
    while sum(alloc) > total:
        i = max((k for k, t in enumerate(tasks) if t[1] == "patterns" and alloc[k] > 0.5),
                key=lambda k: alloc[k], default=None)
        if i is None:
            break
        alloc[i] -= 0.5

    plan = [{"day": d + 1, "hours": hours_per_day, "items": []} for d in range(days)]
    day, left = 0, hours_per_day
    for (label, kind, _), hrs in zip(tasks, alloc):
        while hrs > 0 and day < days:
            chunk = min(hrs, left)
            plan[day]["items"].append({"task": label, "kind": kind, "hours": chunk})
            hrs, left = hrs - chunk, left - chunk
            if left <= 0:
                day, left = day + 1, hours_per_day
    return [p for p in plan if p["items"]]
