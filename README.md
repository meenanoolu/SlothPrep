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