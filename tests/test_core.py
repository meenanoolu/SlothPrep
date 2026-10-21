import pytest
from dataclasses import dataclass

from src import gap, repos, repo_questions


@dataclass
class Q:
    title: str
    frequency: float = 50.0
    topics: list = None


QS = [Q(t) for t in ["Two Sum", "LRU Cache Design", "Merge Intervals", "Course Schedule Graph", "Longest Substring",
                     "Binary Tree Traversal", "Coin Change", "Permutations", "Word Ladder", "Climbing Stairs"]]
GAPS = [{"skill": s, "weight": w, "status": "gap", "evidence": []} for s, w in [("A", 3), ("B", 2), ("C", 2), ("D", 1)]]


@pytest.mark.parametrize("days,hours", [(14, 2), (7, 1), (3, 2), (1, 2), (1, 0.5), (60, 12)])
def test_plan_fits_budget_and_keeps_mock(days, hours):
    plan = gap.build_plan(QS, GAPS, days, hours)
    kinds = [i["kind"] for d in plan for i in d["items"]]
    assert "mock" in kinds
    assert sum(i["hours"] for d in plan for i in d["items"]) <= days * hours + 1e-9
    assert all(sum(i["hours"] for i in d["items"]) <= hours + 1e-9 for d in plan)


def test_plan_keeps_repo_defense_when_squeezed():
    kinds = [i["kind"] for d in gap.build_plan(QS, GAPS, 1, 2) for i in d["items"]]
    assert "repos" in kinds


def test_keyword_matching_is_whole_token():
    assert not repos._has("rag", "storage drag")
    assert not repos._has("react", "a reaction")
    assert repos._has("rag", "uses rag pipeline")
    assert repos._has("def test_", "def test_login():")


def test_pick_code_files_prefers_entrypoints_and_skips_tests():
    tree = {"src/main.py": 5000, "src/distance.py": 3000, "tests/test_a.py": 9000,
            "src/tiny.py": 50, "src/a_long_helper_name.py": 4000, "README.md": 100}
    picked = repos.pick_code_files(tree)
    assert picked[0] == "src/main.py"
    assert "src/distance.py" in picked  # "dist" substring no longer excludes it
    assert "tests/test_a.py" not in picked and "src/tiny.py" not in picked


def test_username_validation():
    assert repos.USERNAME_RE.match("meenanoolu")
    assert not repos.USERNAME_RE.match("../etc")
    assert not repos.USERNAME_RE.match("a/b")


def test_guard_only_accepts_files_the_model_saw(monkeypatch):
    repo = {"name": "r", "readme_excerpt": "", "files": {"a.py": "x" * 10, "b.py": "y" * 10, "c.py": ""}}
    monkeypatch.setattr(repo_questions.llm, "chat_json", lambda s, u: [
        {"file": "a.py", "question": "q1"}, {"file": "c.py", "question": "unseen"}, {"file": "zzz.py", "question": "fake"}])
    out = repo_questions.generate(repo)
    assert [q["file"] for q in out] == ["a.py"]


def test_budget_is_split_across_files():
    repo = {"files": {"a.py": "a" * 10000, "b.py": "b" * 10000}}
    text, shown = repo_questions._code_block(repo, max_chars=1000)
    assert shown == ["a.py", "b.py"] and "### b.py" in text
