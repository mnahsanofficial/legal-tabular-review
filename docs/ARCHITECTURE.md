# Legal Tabular Review — Architecture Design

## 1. High-Level System Architecture

The system is a **full-stack legal document review application** with clear separation between:

- **Frontend (Next.js)**: Project management, document upload/list, tabular review UI, field template management, and export.
- **Backend (Python FastAPI)**: REST API for projects, documents, field templates, extraction, and table/export generation.
- **Storage (in-memory)**: Python dict-based in-memory stores for projects, documents, templates, and extracted records; no persistent database.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Next.js Frontend                                    │
│  Projects │ Documents │ Field Templates │ Table Review │ Export (CSV/Excel)   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ HTTP/REST
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Python FastAPI Backend                                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │   Projects   │ │  Documents    │ │   Templates  │ │ Extraction +        │ │
│  │   routes     │ │  + Parser     │ │   routes     │ │ Normalization       │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐                                         │
│  │ Table/Review  │ │   Export     │                                         │
│  │   routes      │ │   (CSV/XLSX) │                                         │
│  └──────────────┘ └──────────────┘                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ in-memory dicts
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        In-memory data stores                                  │
│  PROJECTS │ DOCUMENTS (by project_id) │ TEMPLATES │ EXTRACTED (by doc_id)   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Component Boundaries

| Component | Responsibility | Boundaries |
|-----------|----------------|------------|
| **Ingestion** | Accept document paths, parse HTML/PDF/TXT to plain text, store document metadata and content in `DOCUMENTS`. | Parser in `app.py`; path validation and extension checks; no extraction logic. |
| **Extraction** | Run field extraction per document using the active field template; produce value, citation, confidence, normalized value. | Extraction logic reads template + document content; writes to `EXTRACTED` keyed by document id. |
| **Normalization** | Map extracted values to a unified schema (dates, party names); applied in the normalizer before persisting. | Normalizer used inside extraction pipeline; same process. |
| **Storage** | Hold projects, documents, templates, extracted fields, review status in memory. | In-memory dicts: `PROJECTS`, `DOCUMENTS`, `TEMPLATES`, `EXTRACTED`; no DB. To add persistence, replace these with DB access (e.g. PostgreSQL) in the same FastAPI app. |
| **Review** | Serve side-by-side table (rows = fields, columns = documents), accept PATCH for status/manual value per cell. | Table built by aggregating `EXTRACTED` and project documents; updates scoped to the project’s documents. |

**Data flow (summary):**

1. **Upload** → Document stored in `DOCUMENTS[project_id]` (path, content, status).
2. **Extract** → For each document + template: run extraction → normalize → write to `EXTRACTED[doc_id]`; set status = `extracted`.
3. **Review** → Table API reads from `EXTRACTED` and documents; PATCH updates only cells for documents in the given project.
4. **Export** → Same table data streamed as CSV or Excel.

## 3. Data Flow: Document Upload → Extraction → Table View

```
[User]                [Frontend]              [Backend (FastAPI)]        [In-memory stores]
   │                       │                       │                              │
   │  Create project       │                       │                              │
   │─────────────────────>│  POST /projects       │                              │
   │                       │──────────────────────>│  PROJECTS[pid] = {...}       │
   │                       │                       │─────────────────────────────>│
   │                       │<──────────────────────│                              │
   │  Add documents        │  POST /projects/:id/documents (paths)                │
   │─────────────────────>│──────────────────────>│  Parse → DOCUMENTS[pid].append│
   │                       │                       │─────────────────────────────>│
   │  Set template         │  PUT /projects/:id/template                          │
   │─────────────────────>│──────────────────────>│  PROJECTS[pid].templateId     │
   │                       │                       │─────────────────────────────>│
   │  Run extraction       │  POST /projects/:id/extract                          │
   │─────────────────────>│──────────────────────>│  EXTRACTED[doc_id] = [...]    │
   │                       │<──────────────────────│                              │
   │  View table           │  GET /projects/:id/table                             │
   │─────────────────────>│──────────────────────>│  Aggregate from EXTRACTED     │
   │                       │<──────────────────────│  + DOCUMENTS, TEMPLATES      │
   │  Export               │  GET /projects/:id/export?format=csv|xlsx            │
   │─────────────────────>│──────────────────────>│  Build file from table data   │
```

## 4. Storage Strategy

- **Current**: In-memory Python dicts. `PROJECTS`, `DOCUMENTS` (list per project_id), `TEMPLATES`, `EXTRACTED` (list per document_id). No persistence across process restarts.
- **Document content**: Stored in each document dict as `content` (parsed text) so re-extraction does not re-read files. Path and status stored for display and validation.
- **Field templates**: Stored in `TEMPLATES` by id; each has `name` and `fields` (list of field definitions). Default template can be ensured idempotently by name (e.g. "Legal Contract Core").
- **Where to change**: All storage lives in `backend/app.py`. To add a database, introduce a persistence layer (e.g. SQLAlchemy, asyncpg) and replace reads/writes to these dicts with DB calls; API and route contracts can stay the same.

**Design decisions (short):**

- **FastAPI + in-memory**: Single app file; routes and stores in one place for clarity. Easy to swap to PostgreSQL later by replacing dict access.
- **Single extraction path**: Rule-based + mock extraction in one place; easy to plug in LLM later.
- **Normalization in pipeline**: Every extracted field gets `normalized_value` before being stored in `EXTRACTED`.
- **Table as read model**: Table endpoint aggregates from `EXTRACTED` and project documents; no separate “table” store.
- **Export from same data**: CSV/Excel built from the same aggregation as the table API.
