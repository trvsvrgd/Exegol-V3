"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import ActionQueue from "../components/ActionQueue";
import BacklogBoard from "../components/BacklogBoard";
import QuickAddTask from "../components/QuickAddTask";
import ThrawnInteraction from "../components/ThrawnInteraction";
import FleetHealth from "../components/FleetHealth";

interface Repo {
  repo_path: string;
  model_routing_preference: string;
  priority: number;
  agent_status: string;
}

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchRepos = useCallback(() => {
    fetch("http://localhost:8000/repos")
      .then((res) => {
        if (!res.ok) throw new Error("Repo request failed");
        return res.json();
      })
      .then((data) => {
        setRepos(data);
        if (data.length > 0 && !activeRepo) {
          setActiveRepo(data[0].repo_path);
        }
      })
      .catch((err) => {
        console.error("Failed to fetch repos:", err);
        setFetchError("Unable to load repository list. Check backend connectivity.");
      });
  }, [activeRepo]);

  useEffect(() => {
    fetchRepos();
  }, [fetchRepos]);

  const activeRepoMeta = repos.find((repo) => repo.repo_path === activeRepo);
  const friendlyName = activeRepoMeta
    ? activeRepoMeta.repo_path.split("/").slice(-1)[0]
    : "No repo selected";

  return (
    <div className="container-fluid">
      <div className="tower-layout">
        <main className="dashboard-region">
          <header className="tower-header">
            <div>
              <h1 className="title-glow">Exegol Control Tower</h1>
              <p className="subtitle">Command the autonomous agent fleet, inspect repo health, and guide the next user intent.</p>
            </div>
            <div className="nav-controls">
              <Link href="/fleet" className="btn-outline">Fleet Dashboard</Link>
              <Link href="/settings" className="btn-outline">Agent Settings</Link>
              <Link href="/costs" className="btn-outline">Cost Management</Link>
            </div>
          </header>

          <section className="hero-panel glass">
            <div className="hero-copy">
              <span className="eyebrow">Workbench Overview</span>
              <h2>{friendlyName}</h2>
              <p>Selected repository and workspace status for current model orchestration.</p>
            </div>
            <div className="hero-actions">
              <div className="repo-selector">
                {repos.map((repo) => {
                  const label = repo.repo_path.split("/").slice(-1)[0];
                  return (
                    <button
                      key={repo.repo_path}
                      className={`repo-pill ${repo.repo_path === activeRepo ? "active" : ""}`}
                      onClick={() => setActiveRepo(repo.repo_path)}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>

              {activeRepoMeta ? (
                <div className="repo-summary-grid">
                  <div className="summary-card">
                    <span>Model routing</span>
                    <strong>{activeRepoMeta.model_routing_preference}</strong>
                  </div>
                  <div className="summary-card">
                    <span>Priority level</span>
                    <strong>{activeRepoMeta.priority}</strong>
                  </div>
                  <div className="summary-card">
                    <span>Agent status</span>
                    <strong>{activeRepoMeta.agent_status || "unknown"}</strong>
                  </div>
                </div>
              ) : (
                <div className="repo-empty-state">Select a repository to load live telemetry and operations.</div>
              )}
            </div>
          </section>

          {fetchError && <div className="error-banner">{fetchError}</div>}

          <section className="sector-grid">
            <div className="sector">
              <h2 className="sector-title">Fleet Command Telemetry</h2>
              <FleetHealth onSelect={setActiveRepo} activePath={activeRepo} />
            </div>

            {activeRepo && (
              <div className="sector">
                <h2 className="sector-title">Operational Intel</h2>
                <QuickAddTask repoPath={activeRepo} onTaskAdded={fetchRepos} />
                <BacklogBoard repoPath={activeRepo} />
                <ThrawnInteraction repoPath={activeRepo} />
              </div>
            )}
          </section>
        </main>

        <aside className="vader-sidebar">
          {activeRepo ? (
            <ActionQueue repoPath={activeRepo} />
          ) : (
            <div className="sidebar-empty">
              <h3>Action Queue</h3>
              <p>Select a repository to review pending human interventions and queues.</p>
            </div>
          )}
        </aside>
      </div>

      <style jsx>{`
        .container-fluid {
          min-height: 100vh;
        }
        .tower-layout {
          display: grid;
          grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.65fr);
          height: 100vh;
          overflow: hidden;
          gap: 1.5rem;
          padding: 1.5rem;
        }
        .dashboard-region {
          overflow-y: auto;
          padding: 2rem;
          border-radius: 24px;
          background: linear-gradient(180deg, rgba(14, 14, 14, 0.98), rgba(7, 7, 7, 0.98));
          box-shadow: 0 20px 80px rgba(0, 0, 0, 0.35);
        }
        .vader-sidebar {
          background: rgba(8, 8, 8, 0.95);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 24px;
          padding: 1.2rem;
          height: calc(100vh - 3rem);
          overflow: hidden;
        }
        .tower-header {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          gap: 1.5rem;
          align-items: flex-start;
          margin-bottom: 2rem;
        }
        .subtitle {
          color: var(--text-secondary);
          font-size: 0.96rem;
          margin-top: 0.5rem;
          max-width: 560px;
          line-height: 1.6;
        }
        .hero-panel {
          display: grid;
          grid-template-columns: 1.2fr 1fr;
          gap: 1.5rem;
          padding: 1.75rem;
          margin-bottom: 2rem;
          border-radius: 24px;
          background: rgba(25, 25, 25, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .hero-copy {
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 1rem;
        }
        .eyebrow {
          font-size: 0.75rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: var(--accent-color);
        }
        .hero-copy h2 {
          margin: 0;
          font-size: 2rem;
          line-height: 1.1;
        }
        .hero-copy p {
          color: var(--text-secondary);
          max-width: 520px;
          line-height: 1.7;
        }
        .hero-actions {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 1.2rem;
        }
        .repo-selector {
          display: flex;
          flex-wrap: wrap;
          gap: 0.75rem;
        }
        .repo-pill {
          border: 1px solid rgba(255, 255, 255, 0.12);
          background: rgba(255, 255, 255, 0.03);
          color: white;
          padding: 0.75rem 1rem;
          border-radius: 999px;
          cursor: pointer;
          transition: all 0.25s ease;
          font-size: 0.9rem;
        }
        .repo-pill.active {
          background: rgba(230, 0, 0, 0.18);
          border-color: rgba(230, 0, 0, 0.35);
          color: var(--accent-color);
          box-shadow: 0 0 16px rgba(230, 0, 0, 0.18);
        }
        .repo-summary-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 1rem;
        }
        .summary-card {
          padding: 1rem;
          border-radius: 18px;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.07);
        }
        .summary-card span {
          color: var(--text-secondary);
          display: block;
          margin-bottom: 0.65rem;
          font-size: 0.75rem;
          letter-spacing: 0.8px;
          text-transform: uppercase;
        }
        .summary-card strong {
          font-size: 1.05rem;
          color: white;
          display: block;
          line-height: 1.4;
        }
        .repo-empty-state {
          color: var(--text-secondary);
          background: rgba(255, 255, 255, 0.03);
          border: 1px dashed rgba(255, 255, 255, 0.12);
          border-radius: 16px;
          padding: 1rem;
        }
        .error-banner {
          margin: 1rem 0 2rem;
          padding: 1rem 1.2rem;
          border-radius: 16px;
          background: rgba(255, 46, 84, 0.1);
          color: #ff8aa2;
          border: 1px solid rgba(255, 46, 84, 0.2);
        }
        .sector-grid {
          display: grid;
          grid-template-columns: 1fr 0.95fr;
          gap: 1.5rem;
        }
        .sector {
          display: flex;
          flex-direction: column;
          min-height: 0;
        }
        .sector-title {
          font-size: 0.78rem;
          text-transform: uppercase;
          color: #888;
          letter-spacing: 1.8px;
          margin-bottom: 1.25rem;
          padding-left: 0.5rem;
          border-left: 2px solid rgba(255, 255, 255, 0.08);
        }
        .sidebar-empty {
          color: var(--text-secondary);
          padding: 1.5rem;
          font-size: 0.95rem;
          line-height: 1.7;
        }

        @media (max-width: 1180px) {
          .tower-layout {
            grid-template-columns: 1fr;
            height: auto;
          }
          .vader-sidebar {
            height: auto;
          }
          .sector-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
