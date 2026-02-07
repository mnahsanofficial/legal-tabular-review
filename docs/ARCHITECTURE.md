# Legal Tabular Review — Architecture Design

## 1. High-Level System Architecture

The system is a **full-stack legal document review application** with clear separation between:

- **Frontend (Next.js)**: Project management, document upload/list, tabular review UI, field template management, and export.
- **Backend (NestJS)**: REST API for projects, documents, field templates, extraction, and table/export generation.
- **Storage (PostgreSQL)**: Persistent storage for projects, documents, templates, extracted records, and review state.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Next.js Frontend                                   │
│  Projects │ Documents │ Field Templates │ Table Review │ Export (CSV/Excel)  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ HTTP/REST
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NestJS Backend                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐ │
│  │   Projects   │ │  Documents    │ │   Templates  │ │ Extraction Service │ │
│  │   Module     │ │   Module      │ │   Module     │ │ + Normalization     │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐                                          │
│  │ Table/Review │ │   Export     │                                          │
│  │   Module     │ │   Service    │                                          │
│  └──────────────┘ └──────────────┘                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │ TypeORM
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PostgreSQL                                          │
│  projects │ documents │ field_templates │ extracted_fields │ review_state   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 2. Component Boundaries

| Component | Responsibility | Boundaries |
|-----------|----------------|------------|
| **Ingestion** | Accept file uploads (or reference paths), parse HTML/PDF/TXT to plain text + structure, store document metadata and raw/parsed content. | Document module + parser service; no extraction logic. |
| **Extraction** | Run field extraction per document using the active field template; produce value, citation, confidence, raw text. | Extraction service reads template + document content; stateless per run. |
| **Normalization** | Map extracted values to a unified schema (dates, party names, enums); applied immediately after extraction. | Normalization lives inside extraction service or a dedicated normalizer; same process. |
| **Storage** | Persist projects, documents, templates, extracted fields, review status. | TypeORM entities and repositories; single DB. |
| **Review** | Serve side-by-side table (rows = fields, columns = documents), accept status transitions (e.g. pending → extracted → reviewed), store manual overrides. | Table module aggregates extracted data; review state stored per field per document. |

**Data flow (summary):**

1. **Upload** → Document stored (path or content), status = `pending`.
2. **Extract** → For each document + template: run extraction → normalize → save extracted fields with citation + confidence; status = `extracted`.
3. **Review** → Table API returns rows (fields) × columns (documents); user can set status (e.g. `confirmed` / `rejected` / `manual_updated`) and optional manual value.
4. **Export** → Table data (including manual overrides) exported to CSV or Excel.

## 3. Data Flow: Document Upload → Extraction → Table View

```
[User]                [Frontend]              [Backend]                    [DB]
   │                       │                       │                         │
   │  Create project       │                       │                         │
   │─────────────────────>│  POST /projects       │                         │
   │                       │──────────────────────>│  INSERT project         │
   │                       │                       │────────────────────────>│
   │                       │<──────────────────────│                         │
   │  Add documents        │  POST /projects/:id/documents (path or file)    │
   │─────────────────────>│──────────────────────>│  Parse → INSERT docs    │
   │                       │                       │────────────────────────>│
   │  Set/select template  │  PUT /projects/:id/template                      │
   │─────────────────────>│──────────────────────>│  Link template          │
   │                       │                       │────────────────────────>│
   │  Run extraction       │  POST /projects/:id/extract                     │
   │─────────────────────>│──────────────────────>│  For each doc:           │
   │                       │                       │  - Extract fields       │
   │                       │                       │  - Normalize            │
   │                       │                       │  - INSERT extracted_*   │
   │                       │<──────────────────────│                         │
   │  View table           │  GET /projects/:id/table                        │
   │─────────────────────>│──────────────────────>│  JOIN fields × docs     │
   │                       │<──────────────────────│  Rows=fields, Cols=docs │
   │  Export               │  GET /projects/:id/export?format=csv|excel      │
   │─────────────────────>│──────────────────────>│  Build file, stream      │
```

## 4. Storage Strategy

- **Database**: PostgreSQL. Chosen for the required tech stack, ACID guarantees, and simple relational model (projects → documents, templates → extracted_fields, review_state).
- **Why not in-memory only**: Assignment allows in-memory/JSON for a skeleton; we use PostgreSQL to satisfy the stack requirement and to demonstrate a realistic persistence layer. Migrations define schema; seed or demo script can load sample data from `data/`.
- **Document content**: Stored as text (parsed from HTML/PDF/TXT) in `documents.content` or `documents.parsed_content` to avoid re-parsing on re-extraction. File binaries can be omitted in skeleton (reference by path or store path).
- **Field template**: Stored in DB with version id; template JSON/YAML structure in a column or separate `field_templates` table. Re-extraction is triggered when template is updated (template version change or explicit “re-extract” action).

**Design decisions (short):**

- **NestJS + TypeORM**: Fits required stack; modules map to ingestion, extraction, templates, table, export.
- **Single extraction service**: Rule-based + mock extraction in one place; easy to swap for LLM later.
- **Normalization inside extraction pipeline**: Ensures every extracted field has a `normalized_value` before persistence; keeps schema unified.
- **Table as a read model**: Table endpoint aggregates from `extracted_fields` + `documents` + optional review overrides; no duplicate storage of “table” state.
- **Export from same table model**: CSV/Excel generated from the same dataset as the table API to guarantee consistency.
