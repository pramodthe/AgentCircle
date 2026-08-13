# AgentCircle API Tester

A small Streamlit UI for hitting the FastAPI backend without the React SPA.

## Run

Terminal 1 — API:

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

Terminal 2 — tester:

```bash
cd tools/api_tester
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Or one-shot with uv:

```bash
cd tools/api_tester
uv run --with streamlit --with httpx streamlit run app.py
```

Open http://localhost:8501. Default API base is `http://localhost:8000`.
