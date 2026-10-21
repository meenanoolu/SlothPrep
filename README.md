SlothPrep

Interview prep that does the hunting so you don’t have to.

Google-first demo for the Slow & Steady challenge. Open-source / open-weight AI at the core.

Live

Deploy on Render free → https://slothprep.onrender.com (or your service name)

What works now





Company-wise LeetCode question patterns (recency + frequency)



Web UI focused on Google first



JSON API



Clear “patterns, not guarantees” labeling + attribution

Local run

pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

Open http://localhost:8000 → defaults to Google.

CLI:

python -m src.github_ingest --company google --top 15

Deploy on Render (free)





Push this repo to https://github.com/meenanoolu/SlothPrep



Render → New → Web Service → connect repo



Settings:





Name: slothprep



Build: pip install -r requirements.txt



Start: uvicorn src.main:app --host 0.0.0.0 --port $PORT



Instance: Free



Deploy → open the .onrender.com URL

Next





Reddit + search for interview experiences



Gap map + time-boxed plan



Local open-weight model for repo-aware questions
## Open-weight model (new)

SlothPrep talks to any OpenAI-compatible endpoint, so the model is swappable with env vars:

    ollama pull gemma3:4b
    export LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=gemma3:4b
    export GITHUB_TOKEN=...   # recommended: raises GitHub limit from 60 to 5000 req/h

New endpoints: `/api/llm/status`, `/api/gap/{company}?github=USER`,
`/api/plan/{company}?github=USER&days=14&hours=2`, `/api/repo-questions?github=USER&repo=NAME`,
`POST /api/check-answer`.

What is automatic vs not: the gap map and plan are deterministic (no model). Repo-aware questions and
answer checking need a model; Render free tier cannot run one, so the live demo shows them only when
LLM_BASE_URL points at a reachable open-weight server.
