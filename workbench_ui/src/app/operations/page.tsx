"use client";

import { useEffect, useState } from "react";
import OperationsPanel from "../../components/OperationsPanel";
import { apiGet } from "../api-client";

interface Repo {
  repo_path: string;
}

export default function OperationsPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Repo[]>("/repos").then((data) => {
      setRepos(data);
      if (data[0]) setActiveRepo(data[0].repo_path);
      setLoadError(null);
    }).catch((err) => {
      console.error(err);
      setLoadError("Unable to load repositories. Check that the backend is running on localhost:8000.");
    });
  }, []);

  return (
    <main className="container ops-page">
      <header className="page-header">
        <h1>Operations</h1>
        <select value={activeRepo} onChange={(event) => setActiveRepo(event.target.value)}>
          {repos.map((repo) => (
            <option key={repo.repo_path} value={repo.repo_path}>{repo.repo_path}</option>
          ))}
        </select>
      </header>
      {loadError ? <p className="ops-error">{loadError}</p> : null}
      {activeRepo ? <OperationsPanel repoPath={activeRepo} /> : !loadError ? <p>Loading repositories...</p> : null}
      <style jsx>{`
        .ops-page { padding-top: 2rem; padding-bottom: 4rem; }
        .page-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }
        h1 { margin: 0; color: white; font-size: 2rem; }
        select { max-width: 520px; width: 100%; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.16); color: white; border-radius: 8px; padding: 0.75rem; }
        p { color: var(--text-secondary); }
        .ops-error { color: #fca5a5; }
        @media (max-width: 720px) { .page-header { align-items: flex-start; flex-direction: column; } }
      `}</style>
    </main>
  );
}
