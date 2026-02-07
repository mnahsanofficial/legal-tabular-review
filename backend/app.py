"""
Legal Tabular Review — FastAPI backend.
In-memory storage; same API surface as prior NestJS version for frontend compatibility.
"""
import calendar
import csv
import io
import json
import os
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    from openpyxl import Workbook
    HAS_EXCEL = True
except ImportError:
    HAS_EXCEL = False

app = FastAPI(title="Legal Tabular Review API")

# ----- In-memory store -----
PROJECTS: dict[str, dict] = {}
DOCUMENTS: dict[str, list] = {}  # project_id -> list of doc dicts
TEMPLATES: dict[str, dict] = {}
EXTRACTED: dict[str, list] = {}  # document_id -> list of extracted field dicts

DEFAULT_TEMPLATE = {
    "name": "Legal Contract Core",
    "fields": [
        {"id": "effective_date", "name": "Effective Date", "type": "date", "normalization": "iso_date"},
        {"id": "party_a", "name": "Party A", "type": "party", "normalization": "trim"},
        {"id": "party_b", "name": "Party B", "type": "party", "normalization": "trim"},
        {"id": "document_type", "name": "Document Type", "type": "text", "normalization": "trim"},
        {"id": "governing_law", "name": "Governing Law", "type": "text", "normalization": "trim"},
        {"id": "term_duration", "name": "Term / Duration", "type": "text", "normalization": "trim"},
        {"id": "termination_notice", "name": "Termination Notice", "type": "text", "normalization": "trim"},
    ],
}


# ----- Parser -----
PERMITTED_EXTENSIONS = {".html", ".htm", ".txt", ".pdf"}
# Base directory for allowed document paths; resolved path must be under this to prevent path traversal.
# Set DOCUMENTS_BASE_DIR to the repo root (or parent of cwd) to allow e.g. ../data/ when running from backend/.
DOCUMENTS_BASE_DIR = Path(os.environ.get("DOCUMENTS_BASE_DIR", ".")).resolve()


def parse_from_path(file_path: str) -> tuple[str | None, str | None]:
    """Return (content, error). Path is resolved and must be under DOCUMENTS_BASE_DIR; only .html, .htm, .txt, .pdf allowed."""
    # Resolve to absolute path
    if os.path.isabs(file_path):
        resolved = Path(file_path).resolve()
    else:
        resolved = (Path.cwd() / file_path).resolve()

    # Restrict to permitted extensions before any file access
    ext = resolved.suffix.lower()
    if ext not in PERMITTED_EXTENSIONS:
        return None, f"Unsupported type: {ext}"

    # Enforce that resolved path is under the allowed base directory (prevent path traversal)
    try:
        resolved.relative_to(DOCUMENTS_BASE_DIR)
    except ValueError:
        return None, "File not allowed"

    if not resolved.exists():
        return None, f"File not found: {file_path}"
    if not resolved.is_file():
        return None, f"Not a file: {file_path}"

    try:
        raw = resolved.read_text(encoding="utf-8", errors="replace")[: 2 * 1024 * 1024]
    except Exception as e:
        return None, str(e)

    if ext in (".html", ".htm"):
        text = re.sub(r"<script[\s\S]*?</script>", "", raw, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').strip()
        return text, None
    if ext == ".txt":
        return raw.strip(), None
    if ext == ".pdf":
        name = resolved.name
        return f"[PDF: {name}] Mock text. Effective Date: January 15, 2020. Party A: Acme Corp. Party B: Beta Inc. Document Type: Supply Agreement. Governing Law: Delaware. Term: 3 years. Termination Notice: 90 days.", None
    return None, f"Unsupported type: {ext}"


# ----- Normalizer -----
MONTHS = {
    "january": "01", "jan": "01", "february": "02", "feb": "02", "march": "03", "mar": "03",
    "april": "04", "apr": "04", "may": "05", "june": "06", "jun": "06", "july": "07", "jul": "07",
    "august": "08", "aug": "08", "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10", "november": "11", "nov": "11", "december": "12", "dec": "12",
}


def to_iso_date(s: str) -> str | None:
    s = s.strip()
    for name, mm in MONTHS.items():
        m = re.search(rf"(\d{{1,2}})?\s*{name}\s*(\d{{1,2}})?,?\s*(\d{{4}})", s, re.I)
        if m:
            try:
                year = int(m.group(3))
                month = int(mm)
                day_val = int(m.group(1) or m.group(2) or "1")
            except (ValueError, TypeError):
                continue
            _, last_day = calendar.monthrange(year, month)
            if not (1 <= day_val <= last_day):
                continue
            return f"{year}-{mm}-{day_val:02d}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    return None


def normalize_field(field_def: dict, raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    t = raw.strip()
    norm = field_def.get("normalization") or field_def.get("type", "")
    if norm == "iso_date" or field_def.get("type") == "date":
        return to_iso_date(t) or t
    return t


# ----- Extraction -----
def infer_page(content: str, pos: int) -> str | None:
    start = max(0, pos - 200)
    chunk = content[start : pos + 200]
    m = re.search(r"page\s*(\d+)(?:\s*of\s*\d+)?", chunk, re.I)
    return f"Page {m.group(1)}" if m else None


def extract_one(content: str, field: dict, doc_name: str) -> dict:
    fid = field["id"]
    lower = content.lower()
    value, citation, confidence = None, doc_name, 0.0

    if fid == "effective_date":
        for pat in [
            r"effective\s+as\s+of\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
            r'effective\s+date\s*[:\("]\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r"([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        ]:
            m = re.search(pat, content, re.I)
            if m:
                value = m.group(1).strip()
                pg = infer_page(lower, content.find(m.group(0)))
                citation = f"{doc_name}, {pg}" if pg else doc_name
                confidence = 0.9
                break
    elif fid == "party_a":
        m = re.search(r"by\s+and\s+between\s+([^,]+(?:,\s*(?:a\s+[^,]+))?),?\s+on\s+the\s+one\s+hand", content, re.I)
        if m:
            value, citation, confidence = m.group(1).strip(), doc_name, 0.95
        else:
            m = re.search(r"(?:between|by)\s+([A-Z][^,]+(?:,\s*(?:a\s+[A-Za-z]+)\s+corporation[^.]*)?)", content, re.I)
            if m:
                value, citation, confidence = m.group(1).strip(), doc_name, 0.85
    elif fid == "party_b":
        m = re.search(r"on\s+the\s+other\s+hand,?\s+and\s+([^.]+)\.", content, re.I)
        if m:
            value, citation, confidence = m.group(1).strip(), doc_name, 0.95
        else:
            m = re.search(r"(?:and|with)\s+([A-Z][^,]+)(?:\.|,)", content, re.I)
            if m:
                value = m.group(1).rstrip(".,").strip()
                citation, confidence = doc_name, 0.7
    elif fid == "document_type":
        if "general terms and conditions" in lower:
            value, citation, confidence = "General Terms and Conditions", doc_name, 0.95
        elif "supply agreement" in lower:
            value, citation, confidence = "Supply Agreement", doc_name, 0.9
        else:
            m = re.search(r"exhibit\s+[\d.]+\s*[-:]?\s*([^\n<]+)", content, re.I)
            if m:
                value, citation, confidence = m.group(1).strip(), doc_name, 0.85
    elif fid == "governing_law":
        m = re.search(r"governing\s+law[:\s]+([^.]+)", content, re.I) or re.search(r"law\s+of\s+the\s+([^.]+)", content, re.I)
        if m:
            value, citation, confidence = m.group(1).strip(), doc_name, 0.9
        elif "delaware" in lower:
            value, citation, confidence = "Delaware", doc_name, 0.7
    elif fid == "term_duration":
        m = re.search(r"(\d+)\s*year", content, re.I)
        if m:
            value, citation, confidence = m.group(0), doc_name, 0.85
        elif re.search(r"during\s+the\s+term", content, re.I):
            value, citation, confidence = "During the Term", doc_name, 0.6
    elif fid == "termination_notice":
        m = re.search(r"(\d+)\s*day\s*[\s']*notice", content, re.I) or re.search(r"notice\s+of\s+(\d+)\s*day", content, re.I)
        if m:
            value, citation, confidence = f"{m.group(1)} days", doc_name, 0.9

    return {
        "value": value,
        "citation": citation,
        "confidence": round(confidence, 2),
        "normalizedValue": normalize_field(field, value),
    }


def run_extraction(doc: dict, template: dict) -> list[dict]:
    content = doc.get("content") or ""
    doc_id = doc["id"]
    doc_name = doc["name"]
    EXTRACTED[doc_id] = []
    for field in template["fields"]:
        out = extract_one(content, field, doc_name)
        EXTRACTED[doc_id].append({
            "documentId": doc_id,
            "fieldId": field["id"],
            "value": out["value"],
            "citation": out["citation"],
            "confidence": out["confidence"],
            "normalizedValue": out["normalizedValue"],
            "reviewStatus": "pending",
            "manualValue": None,
            "manualCitation": None,
        })
    doc["status"] = "extracted"
    return EXTRACTED[doc_id]


# ----- Table -----
def get_table(project_id: str) -> dict:
    project = PROJECTS.get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    template_id = project.get("templateId")
    docs = DOCUMENTS.get(project_id, [])
    if not template_id:
        return {"fields": [], "documents": [{"id": d["id"], "name": d["name"]} for d in docs], "rows": []}
    template = TEMPLATES.get(template_id)
    if not template:
        return {"fields": [], "documents": [{"id": d["id"], "name": d["name"]} for d in docs], "rows": []}
    fields = template["fields"]
    by_doc_field: dict[tuple[str, str], dict] = {}
    for d in docs:
        for ef in EXTRACTED.get(d["id"], []):
            by_doc_field[(d["id"], ef["fieldId"])] = ef
    rows = []
    for f in fields:
        cells = []
        for d in docs:
            ef = by_doc_field.get((d["id"], f["id"]), {})
            display = ef.get("manualValue") or ef.get("value")
            cells.append({
                "documentId": d["id"],
                "value": display,
                "citation": ef.get("manualCitation") or ef.get("citation"),
                "confidence": ef.get("confidence", 0),
                "normalizedValue": ef.get("normalizedValue"),
                "reviewStatus": ef.get("reviewStatus", "pending"),
                "manualValue": ef.get("manualValue"),
            })
        rows.append({"fieldId": f["id"], "fieldName": f["name"], "cells": cells})
    return {
        "fields": [{"id": f["id"], "name": f["name"]} for f in fields],
        "documents": [{"id": d["id"], "name": d["name"]} for d in docs],
        "rows": rows,
    }


def table_to_rows(table: dict) -> list[list[str]]:
    doc_headers = []
    for d in table["documents"]:
        doc_headers.extend([f"{d['name']} (Value)", f"{d['name']} (Citation)", f"{d['name']} (Confidence)"])
    header = ["Field", *doc_headers]
    data_rows = []
    for row in table["rows"]:
        cells = [row["fieldName"]]
        for c in row["cells"]:
            cells.extend([c.get("value") or "", c.get("citation") or "", str(c.get("confidence", ""))])
        data_rows.append(cells)
    return [header, *data_rows]


def escape_csv(s: str) -> str:
    if re.search(r'[",\n\r]', s):
        return '"' + s.replace('"', '""') + '"'
    return s


# ----- Pydantic models -----
class CreateProject(BaseModel):
    name: str
    description: str | None = None


class AddDocuments(BaseModel):
    paths: list[str]


class SetTemplate(BaseModel):
    templateId: str


class UpdateCell(BaseModel):
    documentId: str
    fieldId: str
    reviewStatus: str | None = None
    manualValue: str | None = None
    manualCitation: str | None = None


# ----- Data directory (sample files) -----
DATA_DIR = os.environ.get("DATA_DIR", "../data")


def list_data_files() -> list[dict]:
    """List files in the data directory. Paths are relative to cwd for use with add_documents."""
    data_path = Path(DATA_DIR) if os.path.isabs(DATA_DIR) else Path.cwd() / DATA_DIR
    if not data_path.exists() or not data_path.is_dir():
        return []
    out = []
    base = DATA_DIR.rstrip("/")
    for f in sorted(data_path.iterdir()):
        if f.is_file() and f.suffix.lower() in PERMITTED_EXTENSIONS:
            # Path that parse_from_path can resolve: relative to cwd
            path_str = f"{base}/{f.name}" if base else f.name
            out.append({"path": path_str, "name": f.name})
    return out


# ----- Routes -----
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/data-files")
def get_data_files():
    """List available files in the sample data directory. Use these paths with POST /projects/:id/documents."""
    return list_data_files()


@app.get("/projects")
def list_projects():
    out = []
    for pid, p in PROJECTS.items():
        docs = DOCUMENTS.get(pid, [])
        t = TEMPLATES.get(p.get("templateId") or "") if p.get("templateId") else None
        out.append({
            **p,
            "documents": docs,
            "template": t,
        })
    return sorted(out, key=lambda x: x.get("createdAt", ""), reverse=True)


@app.post("/projects")
def create_project(body: CreateProject):
    pid = str(uuid.uuid4())
    PROJECTS[pid] = {
        "id": pid,
        "name": body.name,
        "description": body.description,
        "templateId": None,
        "createdAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    DOCUMENTS[pid] = []
    return PROJECTS[pid]


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    p = PROJECTS.get(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    docs = DOCUMENTS.get(project_id, [])
    t = TEMPLATES.get(p.get("templateId") or "") if p.get("templateId") else None
    return {**p, "documents": docs, "template": t}


@app.put("/projects/{project_id}/template")
def set_template(project_id: str, body: SetTemplate):
    if project_id not in PROJECTS:
        raise HTTPException(404, "Project not found")
    if body.templateId not in TEMPLATES:
        raise HTTPException(404, "Template not found")
    PROJECTS[project_id]["templateId"] = body.templateId
    return get_project(project_id)


def _normalize_path(fp: str) -> str:
    return str(Path(fp).resolve()) if fp else ""


@app.post("/projects/{project_id}/documents")
def add_documents(project_id: str, body: AddDocuments):
    if project_id not in PROJECTS:
        raise HTTPException(404, "Project not found")
    existing = DOCUMENTS.get(project_id, [])
    existing_paths = {_normalize_path(d["filePath"]) for d in existing}
    added = []
    for fp in body.paths or []:
        norm = _normalize_path(fp)
        if norm in existing_paths:
            continue
        content, err = parse_from_path(fp)
        name = Path(fp).name
        ext = Path(fp).suffix.lower().lstrip(".")
        doc_id = str(uuid.uuid4())
        doc = {
            "id": doc_id,
            "projectId": project_id,
            "name": name,
            "filePath": fp,
            "fileType": ext or None,
            "content": content,
            "status": "failed" if err else "pending",
            "errorMessage": err,
            "createdAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        }
        DOCUMENTS[project_id].append(doc)
        EXTRACTED[doc_id] = []
        added.append(doc)
        existing_paths.add(norm)
    return added


@app.get("/projects/{project_id}/documents")
def list_documents(project_id: str):
    if project_id not in PROJECTS:
        raise HTTPException(404, "Project not found")
    return DOCUMENTS.get(project_id, [])


@app.get("/templates")
def list_templates():
    return list(TEMPLATES.values())


@app.post("/templates/ensure-default")
def ensure_default_template():
    default_name = DEFAULT_TEMPLATE.get("name", "Legal Contract Core")
    for tid, t in TEMPLATES.items():
        if t.get("name") == default_name:
            return t
    tid = str(uuid.uuid4())
    TEMPLATES[tid] = {"id": tid, **DEFAULT_TEMPLATE}
    return TEMPLATES[tid]


@app.post("/templates")
def create_template(body: dict):
    tid = str(uuid.uuid4())
    TEMPLATES[tid] = {"id": tid, "name": body.get("name", ""), "fields": body.get("fields", [])}
    return TEMPLATES[tid]


@app.get("/templates/{template_id}")
def get_template(template_id: str):
    if template_id not in TEMPLATES:
        raise HTTPException(404, "Template not found")
    return TEMPLATES[template_id]


@app.post("/projects/{project_id}/extract")
def extract(project_id: str):
    if project_id not in PROJECTS:
        raise HTTPException(404, "Project not found")
    p = PROJECTS[project_id]
    tid = p.get("templateId")
    if not tid:
        return {"ok": False, "error": "No template linked to project"}
    template = TEMPLATES.get(tid)
    if not template:
        return {"ok": False, "error": "Template not found"}
    results = []
    for doc in DOCUMENTS.get(project_id, []):
        if doc.get("status") == "failed" or not doc.get("content"):
            results.append({"documentId": doc["id"], "documentName": doc["name"], "status": "skipped"})
            continue
        run_extraction(doc, template)
        results.append({"documentId": doc["id"], "documentName": doc["name"], "status": "extracted"})
    return {"ok": True, "results": results}


@app.get("/projects/{project_id}/table")
def get_table_route(project_id: str):
    return get_table(project_id)


@app.patch("/projects/{project_id}/table")
def update_cell(project_id: str, body: UpdateCell):
    if project_id not in PROJECTS:
        raise HTTPException(404, "Project not found")
    project_doc_ids = {d["id"] for d in DOCUMENTS.get(project_id, [])}
    for doc_id in project_doc_ids:
        items = EXTRACTED.get(doc_id, [])
        for ef in items:
            if ef["documentId"] == body.documentId and ef["fieldId"] == body.fieldId:
                if body.reviewStatus is not None:
                    ef["reviewStatus"] = body.reviewStatus
                if body.manualValue is not None:
                    ef["manualValue"] = body.manualValue
                if body.manualCitation is not None:
                    ef["manualCitation"] = body.manualCitation
                return ef
    raise HTTPException(404, "Extracted field not found")


@app.get("/projects/{project_id}/export")
def export_table(project_id: str, format: str = "csv"):
    table = get_table(project_id)
    rows = table_to_rows(table)
    if format == "xlsx" and HAS_EXCEL:
        wb = Workbook()
        ws = wb.active
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=legal-review-table.xlsx"},
        )
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow([str(c) for c in row])
    return StreamingResponse(
        io.BytesIO(("\uFEFF" + buf.getvalue()).encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=legal-review-table.csv"},
    )
