'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useToast } from '@/context/ToastContext';

const API = process.env.NEXT_PUBLIC_API_URL || '';

interface Project {
  id: string;
  name: string;
  templateId: string | null;
  documents: { id: string; name: string; status: string; filePath?: string }[];
}

interface Template {
  id: string;
  name: string;
}

interface TableCell {
  documentId: string;
  value: string | null;
  citation: string | null;
  confidence: number;
  normalizedValue: string | null;
  reviewStatus: string;
}

interface TableRow {
  fieldId: string;
  fieldName: string;
  cells: TableCell[];
}

interface TableData {
  fields: { id: string; name: string }[];
  documents: { id: string; name: string }[];
  rows: TableRow[];
}

interface DataFile {
  path: string;
  name: string;
}

const base = () => (typeof window !== 'undefined' ? '/api' : process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000');

export default function ProjectPage() {
  const params = useParams();
  const id = params?.id as string;
  const [project, setProject] = useState<Project | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [table, setTable] = useState<TableData | null>(null);
  const [paths, setPaths] = useState(
    [
      '../data/EX-10.2.html',
      '../data/Supply Agreement.pdf',
      '../data/Tesla, Inc. (Form_ PRE 14A, Received_ 09_05_2025 06_21_37).html',
      '../data/tsla-ex102_486.htm.pdf',
      '../data/tsla-ex103_198.htm.pdf',
      '../data/tsla-ex103_462.htm.pdf',
    ].join('\n')
  );
  const [dataFiles, setDataFiles] = useState<DataFile[]>([]);
  const [selectedDataPaths, setSelectedDataPaths] = useState<Set<string>>(new Set());
  const [addingFromData, setAddingFromData] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const load = () => {
    if (!id) return;
    const b = base();
    Promise.all([
      fetch(`${b}/projects/${id}`).then((r) => r.json()),
      fetch(`${b}/templates`).then((r) => r.json()),
    ])
      .then(([p, t]) => {
        setProject(p);
        setTemplates(Array.isArray(t) ? t : []);
      })
      .catch(() => setProject(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    const b = base();
    fetch(`${b}/data-files`)
      .then((r) => r.json())
      .then((list) => setDataFiles(Array.isArray(list) ? list : []))
      .catch(() => setDataFiles([]));
  }, []);

  useEffect(() => {
    if (!id || !project) return;
    const b = base();
    fetch(`${b}/projects/${id}/table`)
      .then((r) => r.json())
      .then(setTable)
      .catch(() => setTable(null));
  }, [id, project?.documents?.length, project?.templateId]);

  const existingPaths = new Set(
    (project?.documents ?? []).map((d) => d.filePath || d.name)
  );

  const addDocuments = async () => {
    const list = paths.split(/\n/).map((s) => s.trim()).filter(Boolean);
    const toAdd = list.filter((p) => !existingPaths.has(p || ''));
    if (!toAdd.length) {
      if (list.length) toast('All listed paths are already in this project.');
      return;
    }
    const b = base();
    const res = await fetch(`${b}/projects/${id}/documents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: toAdd }),
    });
    if (res.ok) load();
  };

  const addFromDataFolder = async (pathsToAdd: string[]) => {
    const toAdd = pathsToAdd.filter((p) => !existingPaths.has(p || ''));
    if (!toAdd.length) {
      if (pathsToAdd.length) toast('Selected files are already in this project.');
      return;
    }
    setAddingFromData(true);
    const b = base();
    const res = await fetch(`${b}/projects/${id}/documents`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths: toAdd }),
    });
    if (res.ok) {
      load();
      setSelectedDataPaths(new Set());
    }
    setAddingFromData(false);
  };

  const toggleDataFile = (path: string) => {
    setSelectedDataPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const selectAllDataFiles = () => {
    if (selectedDataPaths.size === dataFiles.length) setSelectedDataPaths(new Set());
    else setSelectedDataPaths(new Set(dataFiles.map((f) => f.path)));
  };

  const setTemplate = async (templateId: string) => {
    const b = base();
    await fetch(`${b}/projects/${id}/template`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ templateId }),
    });
    load();
  };

  const runExtract = async () => {
    setExtracting(true);
    const b = base();
    await fetch(`${b}/projects/${id}/extract`, { method: 'POST' });
    setExtracting(false);
    load();
    setTable(null);
    setTimeout(() => {
      fetch(`${b}/projects/${id}/table`).then((r) => r.json()).then(setTable);
    }, 500);
  };

  const exportUrl = (format: 'csv' | 'xlsx') =>
    `${base()}/projects/${id}/export?format=${format}`;

  if (loading || !project) {
    return (
      <main className="page-container project-page">
        <p className="loading-state">Loading…</p>
        <Link href="/" className="breadcrumb">← Projects</Link>
      </main>
    );
  }

  return (
    <main className="page-container project-page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">← Projects</Link>
      </nav>
      <h1 className="page-title">{project.name}</h1>

      <section className="section-card">
        <h2 className="section-title">Documents</h2>

        {dataFiles.length > 0 && (
          <div className="sample-data-block">
            <p className="section-desc">Add files from the sample <code>data/</code> folder — no paths to type.</p>
            <div className="data-files-toolbar">
              <button
                type="button"
                onClick={selectAllDataFiles}
                className="btn btn-sm"
              >
                {selectedDataPaths.size === dataFiles.length ? 'Deselect all' : 'Select all'}
              </button>
              <button
                type="button"
                onClick={() => addFromDataFolder(selectedDataPaths.size ? Array.from(selectedDataPaths) : dataFiles.map((f) => f.path))}
                className="primary btn-sm"
                disabled={addingFromData || dataFiles.length === 0}
              >
                {addingFromData ? 'Adding…' : selectedDataPaths.size ? `Add ${selectedDataPaths.size} selected` : 'Add all'}
              </button>
            </div>
            <ul className="data-files-list">
              {dataFiles.map((f) => (
                <li key={f.path}>
                  <label className="data-file-item">
                    <input
                      type="checkbox"
                      checked={selectedDataPaths.has(f.path)}
                      onChange={() => toggleDataFile(f.path)}
                    />
                    <span className="data-file-name">{f.name}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="section-desc" style={{ marginTop: dataFiles.length ? '1rem' : 0 }}>
          Or use the paths below (one per line). Pre-filled with files from <code>data/</code>. Run the backend from the <code>backend/</code> folder so these paths work.
        </p>
        <textarea
          value={paths}
          onChange={(e) => setPaths(e.target.value)}
          rows={6}
          placeholder="../data/EX-10.2.html"
          aria-label="Document paths"
        />
        <div className="section-actions">
          <button
            type="button"
            onClick={addDocuments}
            className="primary"
            disabled={!paths.trim().replace(/\n/g, '').trim()}
          >
            Add from paths
          </button>
        </div>
        {project.documents?.length > 0 && (
          <ul className="doc-list">
            {project.documents.map((d) => (
              <li key={d.id}>
                <span className="doc-name">{d.name}</span>
                <span className={`doc-status ${d.status}`}>{d.status}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="section-card">
        <h2 className="section-title">Field template</h2>
        <p className="section-desc">Choose the schema used for extraction.</p>
        <select
          value={project.templateId || ''}
          onChange={(e) => setTemplate(e.target.value)}
          disabled={!templates.length}
          aria-label="Field template"
        >
          <option value="">Select template</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        {!templates.length && (
          <div className="section-actions" style={{ marginTop: '0.75rem' }}>
            <button
              type="button"
              onClick={async () => {
                const b = base();
                await fetch(`${b}/templates/ensure-default`, { method: 'POST' });
                const t = await fetch(`${b}/templates`).then((r) => r.json());
                setTemplates(Array.isArray(t) ? t : []);
              }}
            >
              Create default template
            </button>
          </div>
        )}
      </section>

      <section className="section-card">
        <h2 className="section-title">Extraction</h2>
        <p className="section-desc">Run extraction for all documents using the selected template.</p>
        <div className="action-row">
          <button
            type="button"
            onClick={runExtract}
            disabled={!project.templateId || !project.documents?.length || extracting}
            className="primary"
          >
            {extracting ? 'Extracting…' : 'Run extraction'}
          </button>
        </div>
      </section>

      <section className="section-card">
        <h2 className="section-title">Export</h2>
        <p className="section-desc">Download the review table.</p>
        <div className="export-group">
          <a href={exportUrl('csv')} className="btn" download>Download CSV</a>
          <a href={exportUrl('xlsx')} className="btn" download>Download Excel</a>
        </div>
      </section>

      {table && table.rows.length > 0 && (
        <section className="section-card">
          <h2 className="section-title">Review table</h2>
          <p className="section-desc">Side-by-side view: one row per field, one column group per document.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  {table.documents.map((d) => (
                    <th key={d.id} colSpan={3}>{d.name}</th>
                  ))}
                </tr>
                <tr>
                  <th></th>
                  {table.documents.flatMap((d) => [
                    <th key={`${d.id}-v`}>Value</th>,
                    <th key={`${d.id}-c`}>Citation</th>,
                    <th key={`${d.id}-conf`}>Conf.</th>,
                  ])}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row) => (
                  <tr key={row.fieldId}>
                    <td><strong>{row.fieldName}</strong></td>
                    {row.cells.flatMap((cell) => [
                      <td key={`${cell.documentId}-v`}>{cell.value ?? '—'}</td>,
                      <td key={`${cell.documentId}-cit`}>{cell.citation ?? '—'}</td>,
                      <td key={`${cell.documentId}-conf`} className={cell.confidence >= 0.8 ? 'confidence-high' : cell.confidence >= 0.5 ? 'confidence-mid' : 'confidence-low'}>
                        {cell.confidence != null ? Math.round(cell.confidence * 100) + '%' : '—'}
                      </td>,
                    ])}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
