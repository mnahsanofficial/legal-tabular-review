# Legal Tabular Review

A minimal skeleton for a **Legal Tabular Review** application: ingest legal documents, extract key fields into a unified schema, and display results in a side-by-side tabular format with citations and confidence scores. Supports field templates, re-extraction on template change, and export to CSV/Excel.

**Tech stack:** Next.js (frontend), Python FastAPI (backend), in-memory storage.

---

## Project overview

- **Backend (Python FastAPI):** REST API for projects, documents, field templates, extraction, table view, and CSV/Excel export. In-memory storage (no database).
- **Frontend (Next.js):** Project list, project detail with document paths, template selection, run extraction, side-by-side review table, and export links.
- **Extraction:** Rule-based (regex) extraction from HTML/text content; PDF returns mock text for the skeleton. Each field has **value**, **citation**, **confidence**, and **normalized_value**.
- **Table:** One row per field, one column per document; each cell shows value, citation, and confidence. Export uses the same data (including manual overrides when implemented).

---

## Architecture summary

- **Ingestion:** Documents added by path (e.g. `data/EX-10.2.html`). Parser strips HTML or reads text; PDF is mocked. Content stored for extraction.
- **Extraction:** Runs per document using the project’s field template. Rule-based patterns produce value + citation + confidence; normalization (e.g. ISO date) produces `normalized_value`.
- **Storage:** In-memory (Python dicts). Same logical entities: projects, documents, field_templates, extracted_fields. Document status: `pending` → `extracted` (or `failed`).
- **Review:** Table API aggregates extracted fields by field and document. Optional review status and manual value per cell (PATCH table).
- **Export:** CSV and Excel generated from the same table dataset.

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for component boundaries and data flow, and **[docs/FUNCTIONAL_DESIGN.md](docs/FUNCTIONAL_DESIGN.md)** for user flow, API, and edge cases.

---

## How extraction works

- **Field template:** Default template is created via `POST /templates/ensure-default` (effective_date, party_a, party_b, document_type, governing_law, term_duration, termination_notice).
- **Rule-based extractor:** For each template field, the extraction service runs pattern matching (regex) on the document text. Examples: “effective as of &lt;date&gt;”, “by and between &lt;party A&gt; … on the other hand, and &lt;party B&gt;”, “governing law: …”, “N day notice”.
- **Citation:** Set to document name and, when detectable, location (e.g. “Page 1”) derived from nearby text.
- **Confidence:** Heuristic: e.g. 0.95 for strong pattern match, 0.7 for weaker match, 0 for missing.

---

## How confidence and citation are generated

- **Confidence:** Assigned in code per pattern: high (e.g. 0.9–0.95) for precise legal phrasing, lower (e.g. 0.7) for looser matches. No LLM in this skeleton.
- **Citation:** String like `"EX-10.2.html"` or `"EX-10.2.html, Page 1"` when a “Page N” pattern is found near the match. Stored per extracted field.

---

## How to run the demo

### Prerequisites

- Node 18+ (frontend), Python 3.10+ (backend)
- Repo root as working directory

### 1. Backend (Python FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload --port 4000
```

API: **http://localhost:4000**. Health: `GET http://localhost:4000/health`.

### 2. Create default template (once)

```bash
curl -X POST http://localhost:4000/templates/ensure-default
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: **http://localhost:3000**. Uses Next.js rewrites so `/api/*` proxies to the backend.

### 4. End-to-end in the UI

1. Create a project.
2. Open the project; in “Documents”, add paths (e.g. `data/EX-10.2.html`, `data/Supply Agreement.pdf`), then **Add documents**.
3. Select the **Field template** (e.g. “Legal Contract Core”) and **Run extraction**.
4. View the **Review table** and use **Download CSV** or **Download Excel**.

Document paths are relative to the **backend** process current working directory. If you start the backend from the `backend/` directory (`uvicorn app:app --reload --port 4000`), use paths like `../data/EX-10.2.html` so the repo-root `data/` folder is found.

---

## Dataset testing

- **Sample files:** `data/` (e.g. `EX-10.2.html`, `Supply Agreement.pdf`, Tesla HTML/PDFs).
- **Script:** From repo root, with backend running and default template created:

  ```bash
  cd backend && bash scripts/run-dataset-test.sh
  ```

  The script: creates a project, adds documents from `data/`, links the default template, runs extraction, and fetches the table. It prints document count and cell coverage.

- **Checklist:**
  - [ ] All documents ingest (HTML/PDF paths); status moves to `extracted` or `failed`.
  - [ ] Each extracted field has value (or is missing), citation, confidence, and normalized_value where applicable.
  - [ ] Table shows one row per field, one column per document; cells show value, citation, confidence.
  - [ ] Export CSV/Excel matches the table (same rows/columns).
  - [ ] **Template update → re-extraction:** Change the template (e.g. add a field or edit name), call `POST /projects/:id/extract` again; table refreshes with new/updated extractions.

---

## Testing checklist

- [ ] Create project, add documents (paths from `data/`), set template, run extraction.
- [ ] Table loads with correct fields and documents; value, citation, confidence present or marked missing.
- [ ] CSV and Excel download with same structure.
- [ ] PATCH table to set review status or manual value (optional; endpoint exists).
- [ ] Re-extract after template change; table updates.

---

## Known tradeoffs and future improvements

- **PDF:** Not parsed; mock text is returned. Production would use a PDF parser (e.g. pdf-parse, pdfjs) or external service.
- **Extraction:** Rule-based only. For production, add LLM-based extraction behind the same interface (value, citation, confidence, normalized_value).
- **Paths:** Documents are added by path; no multipart file upload in this skeleton. File upload would write to disk and then register paths.
- **Async jobs:** Extraction is synchronous. For large batches, add a job queue and status polling.
- **Review UI:** Table is read-only in the skeleton; PATCH endpoint exists for status/manual value but the UI does not yet expose it.
- **Normalization:** Basic (e.g. ISO date, trim). More fields and rules can be added in the normalizer and template.

---

## API summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET/POST | `/projects` | List / create project |
| GET/PUT | `/projects/:id`, `/projects/:id/template` | Get project / set template |
| POST/GET | `/projects/:id/documents` | Add by paths / list |
| GET/POST | `/templates`, `/templates/ensure-default` | List / create default template |
| POST | `/projects/:id/extract` | Run extraction |
| GET/PATCH | `/projects/:id/table` | Get table / update cell |
| GET | `/projects/:id/export?format=csv\|xlsx` | Download CSV or Excel |

---

## Repository layout

- **backend/** — Python FastAPI app (ingestion, extraction, table, export).
- **frontend/** — Next.js app (project list, project detail, table, export).
- **data/** — Sample legal documents for ingestion and testing.
- **docs/** — ARCHITECTURE.md, FUNCTIONAL_DESIGN.md, REQUIREMENTS.md.
