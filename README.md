# SlothPrep

Interview prep that does the hunting so you don't have to. Google-first demo for the DEV
Slow & Steady challenge, with open-weight AI at the core.

Live: https://slothprep.onrender.com (free tier: the first visit after 15 idle minutes takes ~30-60 s to wake)

## What it does

1. **Question patterns**: company-wise LeetCode lists (recency + frequency) from a community dataset.
2. **Gap map**: your public GitHub repos vs what a Google SWE role leans on. Deterministic keyword evidence, no model.
3. **Day-by-day plan** sized to your days x hours. Deterministic, no model.
4. **Questions about your own code**: an open-weight model reads real files from one repo, asks interview
   questions, and checks your answer against that code. Questions citing files the model never saw are dropped.

## Automatic vs not

| Automatic | Needs you / honest limits |
|---|---|
| Fetching question lists, scanning repos, gap map, plan | Topics are inferred from question titles (crude) |
| Questions + answer checking (when a model is attached) | The live free-tier host cannot run a model; point `LLM_BASE_URL` at one |
| | Gap map sees public repos only, not LeetCode/Codeforces practice; "gap" means no evidence found |
| | Reddit / search-based experience collection is not built; `POST /api/summarize` summarizes pasted posts |

## Run locally

    pip install -r requirements.txt
    uvicorn src.main:app --reload
    # open http://localhost:8000

### Attach an open-weight model

Local Ollama (private, free after download):

    ollama pull gemma3:4b
    export LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=gemma3:4b

Hosted open-weight endpoint (Groq, Together, Fireworks...): set `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.
If `LLM_BASE_URL` is unset, SlothPrep tries Ollama at `127.0.0.1:11434` using `OLLAMA_MODEL`.

Also recommended: `export GITHUB_TOKEN=...` (raises GitHub limit from 60 to 5000 requests/hour).

## API

- `GET /api/health`, `GET /api/llm/status`
- `GET /api/questions/{company}?top=20&window=last_30_days`
- `GET /api/gap/{company}?github=USER`
- `GET /api/plan/{company}?github=USER&days=14&hours=2`
- `GET /api/code-questions?github=USER&repo=NAME&n=4`
- `POST /api/check-answer` with JSON `{github, repo, question, answer}`
- `POST /api/summarize` with JSON `{text, company}`

## Tests

    pip install -r requirements-dev.txt
    pytest

## Deploy on Render (free)

Existing service: push to GitHub and it auto-deploys (or Manual Deploy > Deploy latest commit).
New service: `render.yaml` in this repo works as a Blueprint, or create a Web Service with
build `pip install -r requirements.txt` and start `uvicorn src.main:app --host 0.0.0.0 --port $PORT`.

## Data

Community-maintained GitHub lists (mainly snehasishroy/leetcode-companywise-interview-questions).
Self-reported and NOT official or guaranteed. Treat as patterns only.
