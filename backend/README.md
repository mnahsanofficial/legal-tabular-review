# Legal Tabular Review — Backend (Python FastAPI)

REST API for projects, documents, field templates, extraction, table view, and CSV/Excel export. **In-memory storage** (no database required).

## Setup

- Python 3.10+
- Create a virtualenv (recommended): `python -m venv .venv && source .venv/bin/activate` (or `.venv\Scripts\activate` on Windows)

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 4000
```

API: http://localhost:4000. Health: `GET /health`.

## First run

Create the default field template:

```bash
curl -X POST http://localhost:4000/templates/ensure-default
```

## Document paths

Paths in `POST /projects/:id/documents` are relative to the **process cwd**. When running from `backend/`, use `../data/EX-10.2.html` to point at the repo `data/` folder.

## Dataset test

From repo root (with API running on port 4000):

```bash
cd backend && bash scripts/run-dataset-test.sh
```

Requires `jq`. Uses `../data` by default to find sample documents.
