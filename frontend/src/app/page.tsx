'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

const API = process.env.NEXT_PUBLIC_API_URL || '';

interface Project {
  id: string;
  name: string;
  description: string | null;
  templateId: string | null;
  documents?: { id: string; name: string; status: string }[];
}

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API || '/api'}/projects`)
      .then((r) => r.json())
      .then(setProjects)
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  const createProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const res = await fetch(`${API || '/api'}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (res.ok) {
      const p = await res.json();
      setProjects((prev) => [p, ...prev]);
      setName('');
    }
  };

  return (
    <main className="page-container">
      <header className="page-header">
        <h1>Legal Tabular Review</h1>
        <p className="subtitle">Extract, compare, and review key fields across legal documents.</p>
      </header>

      <section className="form-card">
        <form onSubmit={createProject}>
          <label htmlFor="project-name">New project</label>
          <div className="form-row">
            <input
              id="project-name"
              type="text"
              placeholder="Enter project name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-label="Project name"
            />
            <button type="submit" className="primary" disabled={!name.trim()}>
              Create project
            </button>
          </div>
        </form>
      </section>

      <section aria-label="Projects">
        <h2 className="sr-only">Projects</h2>
        {loading ? (
          <p className="loading-state">Loading projects…</p>
        ) : projects.length === 0 ? (
          <div className="empty-state">
            <strong>No projects yet</strong>
            Create a project above to get started.
          </div>
        ) : (
          <ul className="project-list">
            {projects.map((p) => (
              <li key={p.id} className="project-card">
                <Link href={`/project/${p.id}`} className="project-card-link">
                  <span className="project-card-name">{p.name}</span>
                  <div className="meta">
                    {p.documents?.length != null && p.documents.length > 0 && (
                      <span className="doc-count">
                        {p.documents.length} document{p.documents.length !== 1 ? 's' : ''}
                      </span>
                    )}
                    <span className="arrow" aria-hidden>→</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
