"""GitHub question-list ingestion for SlothPrep."""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests

from .config import (
    ATTRIBUTION,
    DEFAULT_COMPANY,
    SNEHASISHROY_API_CONTENTS,
    SNEHASISHROY_RAW_BASE,
    TIME_WINDOWS,
    USER_AGENT,
)
from .models import CompanyQuestionSet, Question


class GitHubIngestError(Exception):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def list_companies(session: Optional[requests.Session] = None) -> List[str]:
    sess = session or _session()
    resp = sess.get(SNEHASISHROY_API_CONTENTS, timeout=30)
    if resp.status_code != 200:
        raise GitHubIngestError(
            f"Failed to list companies: HTTP {resp.status_code}"
        )
    items = resp.json()
    companies = [
        item["name"]
        for item in items
        if item.get("type") == "dir" and not item["name"].startswith(".")
    ]
    return sorted(companies)


def _parse_pct(value: str) -> Optional[float]:
    if not value or value.strip() == "":
        return None
    try:
        return float(value.replace("%", "").strip())
    except ValueError:
        return None


def _parse_csv_content(
    content: str, window_label: str, source_repo: str = "snehasishroy"
) -> List[Question]:
    questions: List[Question] = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}
        try:
            qid = int(row.get("ID") or row.get("Id") or 0) or None
        except ValueError:
            qid = None
        title = row.get("Title") or row.get("title") or "Unknown"
        url = row.get("URL") or row.get("url") or row.get("Link") or ""
        difficulty = (row.get("Difficulty") or "Unknown").title()
        acceptance = _parse_pct(row.get("Acceptance %") or row.get("Acceptance") or "")
        frequency = _parse_pct(row.get("Frequency %") or row.get("Frequency") or "")
        topics_raw = row.get("Topics") or ""
        topics = [t.strip() for t in topics_raw.split(";") if t.strip()] if topics_raw else []

        questions.append(
            Question(
                id=qid,
                title=title,
                url=url,
                difficulty=difficulty,
                acceptance=acceptance,
                frequency=frequency,
                topics=topics,
                source_window=window_label,
                source_repo=source_repo,
                confidence="medium",
            )
        )
    return questions


def fetch_company(
    company: str,
    windows: Optional[List[str]] = None,
    session: Optional[requests.Session] = None,
    cache_dir: Optional[Path] = None,
    use_cache: bool = True,
) -> CompanyQuestionSet:
    company = company.lower().strip().replace(" ", "-")
    sess = session or _session()
    wanted = windows or list(TIME_WINDOWS.keys())
    result_windows: Dict[str, List[Question]] = {}
    notes: List[str] = []

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)

    for filename in wanted:
        if filename not in TIME_WINDOWS:
            notes.append(f"Unknown window skipped: {filename}")
            continue
        meta = TIME_WINDOWS[filename]
        label = meta["label"]
        url = f"{SNEHASISHROY_RAW_BASE}/{company}/{filename}"

        cache_path = None
        if cache_dir and use_cache:
            cache_path = cache_dir / f"{company}_{filename}"
            if cache_path.exists():
                age = time.time() - cache_path.stat().st_mtime
                if age < 86400:
                    content = cache_path.read_text(encoding="utf-8")
                    result_windows[label] = _parse_csv_content(content, label)
                    continue

        resp = sess.get(url, timeout=30)
        if resp.status_code == 404:
            notes.append(f"No data for window {label} (404)")
            result_windows[label] = []
            continue
        if resp.status_code != 200:
            notes.append(f"Failed {label}: HTTP {resp.status_code}")
            result_windows[label] = []
            continue

        content = resp.text
        if cache_path:
            cache_path.write_text(content, encoding="utf-8")

        result_windows[label] = _parse_csv_content(content, label)
        time.sleep(0.25)

    return CompanyQuestionSet(
        company=company,
        windows=result_windows,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        source_repo="snehasishroy/leetcode-companywise-interview-questions",
        attribution=ATTRIBUTION,
        notes=notes,
    )


def merge_unique_questions(
    qset: CompanyQuestionSet, prefer_window: str = "last_30_days"
) -> List[Question]:
    window_order = sorted(TIME_WINDOWS.values(), key=lambda m: m["priority"])
    seen: Set[str] = set()
    merged: List[Question] = []
    ordered_labels = [prefer_window] + [
        m["label"] for m in window_order if m["label"] != prefer_window
    ]
    for label in ordered_labels:
        for q in qset.windows.get(label, []):
            key = q.url or f"{q.id}:{q.title}"
            if key not in seen:
                seen.add(key)
                merged.append(q)
    return merged


def save_json(qset: CompanyQuestionSet, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(qset.to_dict(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Ingest company-wise LeetCode lists")
    parser.add_argument("--company", default=DEFAULT_COMPANY)
    parser.add_argument("--list-companies", action="store_true")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    sess = _session()
    cache = Path(__file__).resolve().parent.parent / "data" / "cache"

    if args.list_companies:
        companies = list_companies(sess)
        print(f"Found {len(companies)} companies")
        for c in companies[:40]:
            print(f"  {c}")
        sys.exit(0)

    print(f"Fetching: {args.company}")
    qset = fetch_company(args.company, session=sess, cache_dir=cache)
    out = Path("data") / f"{args.company}.json"
    save_json(qset, out)
    print(f"Saved {out}")
    for w, qs in qset.windows.items():
        print(f"  {w}: {len(qs)}")

    print(f"\nTop {args.top} (prefer recent):")
    for i, q in enumerate(merge_unique_questions(qset)[: args.top], 1):
        freq = f"{q.frequency:.0f}%" if q.frequency is not None else "?"
        print(f"  {i}. [{q.difficulty}] {q.title} ({freq}) – {q.source_window}")