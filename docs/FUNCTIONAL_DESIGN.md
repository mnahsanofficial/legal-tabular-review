# Legal Tabular Review — Functional Design

## 1. User Flow

1. **Create project** → User creates a review project (name, optional description).
2. **Add documents** → User uploads files or registers paths (e.g. from `data/`). System parses and stores text/metadata; document status = `pending`.
3. **Configure field template** → User selects or creates a field template (list of legal fields with types and optional rules). Template is linked to the project.
4. **Run extraction** → User triggers extraction for the project. Backend runs extraction per document using the template; writes extracted fields (value, citation, confidence, normalized_value); document status = `extracted`.
5. **Review table** → User sees side-by-side table: one row per field, one column per document. Each cell shows value, citation, confidence; user can set review status and optionally override value.
6. **Export** → User exports the table (including overrides) to CSV or Excel.

**Template update flow:** When the field template is updated (fields added/removed/renamed), user can trigger **re-extraction**. Existing extracted data for unchanged fields can be retained or recomputed; implementation may mark “stale” and re-run extraction for all documents with the new template.

## 2. API Behavior and Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List projects. |
| POST | `/projects` | Create project (body: `name`, optional `description`). |
| GET | `/projects/:id` | Get project with documents and template info. |
| POST | `/projects/:id/documents` | Add document(s): multipart upload or JSON `{ "paths": ["data/EX-10.2.html"] }` for path-based ingestion. |
| GET | `/projects/:id/documents` | List documents and their status. |
| GET | `/templates` | List field templates. |
| POST | `/templates` | Create template (body: template definition). |
| GET | `/templates/:id` | Get template by id. |
| PUT | `/projects/:id/template` | Set project’s active template (body: `templateId`). |
| POST | `/projects/:id/extract` | Run extraction for all documents in project; optionally re-extract after template change. |
| GET | `/projects/:id/table` | Get tabular view: rows = fields, columns = documents; each cell = value, citation, confidence, normalized_value, review status. |
| PATCH | `/projects/:id/table` | Update review state and/or manual value for a field-document pair. |
| GET | `/projects/:id/export?format=csv` | Download table as CSV. |
| GET | `/projects/:id/export?format=xlsx` | Download table as Excel. |

Response shapes (conceptual):

- **Table**: `{ fields: string[], documents: { id, name }[], rows: { fieldId, fieldName, cells: { documentId, value, citation, confidence, normalizedValue, reviewStatus }[] } }`.

## 3. Field Template Lifecycle

- **Create**: User defines a template (name + list of fields). Each field has: `id`, `name`, `type` (e.g. `date`, `text`, `party`, `enum`), optional `validation` or `normalization` hints.
- **Versioning**: Template can have a `version` or `updatedAt`. When linked to a project, project stores `templateId` (and optionally template version at link time).
- **Update**: Editing a template (add/remove/change fields) updates the template record. Projects using it can be flagged for re-extraction.
- **Re-extraction**: Explicit `POST /projects/:id/extract` runs extraction with the current template. All documents in the project are re-processed; existing extracted data is replaced (or merged per implementation). Table view reflects new extractions after re-extraction.

## 4. Status Transitions

- **Document**: `pending` → `extracted` (after successful extraction). If extraction fails, can remain `pending` or move to `failed`.
- **Extraction job**: Optional job status `pending` | `running` | `completed` | `failed` for async behavior; skeleton may do sync extraction and set document status directly.
- **Review (per field per document)**:
  - `pending` — not yet reviewed.
  - `confirmed` — reviewer accepted the extracted value.
  - `rejected` — reviewer rejected (optional manual value stored).
  - `manual_updated` — value was manually set or corrected.
  - `missing_data` — confirmed as missing in document.

Transitions: any → `confirmed` | `rejected` | `manual_updated` | `missing_data`. Manual override stores `manual_value` and optionally `manual_citation`; table and export show manual value when present.

## 5. Edge Cases

| Case | Behavior |
|------|----------|
| **Missing field** | Extraction returns no value or empty; `value`/`normalized_value` null or empty; `confidence` 0 or low; citation empty; review status can be set to `missing_data`. |
| **Conflicting values** | Multiple candidates for same field (e.g. two dates): extraction picks one (e.g. highest confidence or first match); citation points to source; reviewer can set `rejected` + manual value. |
| **Low confidence** | Field stored with low confidence (e.g. &lt; 0.5); table and export still show value + citation; UI can highlight low confidence; reviewer can confirm or override. |
| **Unparseable document** | Parser fails (e.g. corrupted PDF): document status = `failed`; no extracted fields; table shows empty/missing for that column. |
| **Template change** | Re-extraction required to populate new fields or reflect new rules; old extracted data for removed fields can be dropped or ignored in table. |
| **Export with overrides** | Export uses manual value when review status is `manual_updated` or when manual value is set; otherwise uses extracted value. |

## 6. Extraction Output Per Field

Each extracted field (per document) must include:

- **value**: Raw extracted text.
- **citation**: Document reference + location (e.g. document id/name + “page 1”, “Section 1.1”, or “paragraph 3”). Stored as string or structured `{ documentId, page, section }`.
- **confidence**: Number in [0, 1] or percentage; from rule strength or mock.
- **normalized_value**: Value after normalization (e.g. ISO date, trimmed party name, enum code).

All four are persisted and exposed in table and export.
