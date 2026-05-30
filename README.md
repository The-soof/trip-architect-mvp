# Trip Architect MVP

Trip Architect is a full-stack travel planning MVP built from the `plan.md` spec:

- Python `FastAPI` backend
- React + Vite frontend
- SQLite for local development, PostgreSQL-ready for Railway
- Deterministic fallback planner plus native Gemini structured outputs for trip generation
- Tavily + Google Places + Gemini layered research for itinerary, stays, and travel discovery

## Local development

Backend:

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Tests

Backend:

```bash
cd backend
pytest
```

Agent evals are included in the backend pytest suite. To run just the planner/itinerary quality evals:

```bash
cd backend
pytest tests/test_agent_evals.py
```

Frontend:

```bash
cd frontend
npm test
```

## Deployment

The repo includes a root `Dockerfile` for Railway. It builds the React app, installs backend dependencies with Python 3.11, and serves the SPA from FastAPI.
