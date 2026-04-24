"use client";

import { useState, useEffect } from "react";
import ActionQueue from "../components/ActionQueue";
import BacklogBoard from "../components/BacklogBoard";
import QuickAddTask from "../components/QuickAddTask";

interface Repo {
  repo_path: string;
  model_routing_preference: string;
  priority: number;
  agent_status: string;
}

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string | null>(null);

  const fetchRepos = () => {
    fetch("http://localhost:8000/repos")
      .then(res => res.json())
      .then(data => {
        setRepos(data);
        if (data.length > 0 && !activeRepo) {
          setActiveRepo(data[0].repo_path);
        }
      })
      .catch(err => console.error("Failed to fetch repos:", err));
  };

  useEffect(() => {
    fetchRepos();
  }, []);

  return (
    <div className="container-fluid">
      <div className="tower-layout">
        {/* Main Dashboard Area */}
        <main className="dashboard-region">
          <header className="tower-header">
            <div>
              <h1 className="title-glow">Exegol Control Tower</h1>
              <p className="subtitle">Bi-directional orchestrator and fleet management.</p>
            </div>
            <div className="nav-controls">
              <a href="/settings" className="btn-outline">Agent Settings</a>
            </div>
          </header>

          <section className="sector-grid">
            <div className="sector">
              <h2 className="sector-title">Fleet Command</h2>
              <div className="repo-grid">
                {repos.map(repo => (
                  <div 
                    key={repo.repo_path} 
                    className={`glass repo-card ${activeRepo === repo.repo_path ? 'active-border' : ''}`}
                    onClick={() => setActiveRepo(repo.repo_path)}
                  >
                    <div className="repo-header">
                      <h3>{repo.repo_path.split('\\').pop()}</h3>
                      <span className={`status-badge ${repo.agent_status}`}>
                        {repo.agent_status}
                      </span>
                    </div>
                    <div className="repo-details">
                      <div className="detail">
                        <span className="label">Brain:</span>
                        <span className="value title-glow">{repo.model_routing_preference.toUpperCase()}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {activeRepo && (
              <div className="sector">
                <h2 className="sector-title">Operational Intel</h2>
                <QuickAddTask repoPath={activeRepo} onTaskAdded={fetchRepos} />
                <BacklogBoard repoPath={activeRepo} />
              </div>
            )}
          </section>
        </main>

        {/* Sidebar for HITL tasks */}
        <aside className="vader-sidebar">
          {activeRepo && <ActionQueue repoPath={activeRepo} />}
        </aside>
      </div>

      <style jsx>{`
        .container-fluid {
          min-height: 100vh;
        }
        .tower-layout {
          display: grid;
          grid-template-columns: 1fr 400px;
          height: 100vh;
          overflow: hidden;
        }
        .dashboard-region {
          overflow-y: auto;
          padding: 2.5rem;
          background: radial-gradient(circle at 0% 0%, rgba(30, 0, 0, 0.15) 0%, transparent 60%);
        }
        .vader-sidebar {
          background: rgba(10, 10, 10, 0.95);
          border-left: 1px solid var(--border-color);
          padding: 1rem;
          height: 100%;
          overflow: hidden;
        }
        .tower-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 3rem;
        }
        .subtitle {
          color: var(--text-secondary);
          font-size: 0.9rem;
          margin-top: 0.5rem;
        }
        .sector {
          margin-bottom: 3rem;
        }
        .sector-title {
          font-size: 0.8rem;
          text-transform: uppercase;
          color: #555;
          letter-spacing: 2px;
          margin-bottom: 1.5rem;
          padding-left: 0.5rem;
          border-left: 2px solid #555;
        }
        .repo-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 1.5rem;
        }
        .repo-card {
          padding: 1.2rem;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .repo-card:hover {
          background: rgba(255, 255, 255, 0.05);
          transform: translateY(-2px);
        }
        .active-border {
          border-color: var(--accent-color);
          box-shadow: 0 0 15px var(--accent-glow);
        }
        .repo-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .repo-header h3 {
          margin: 0;
          font-size: 1.1rem;
        }
        .status-badge {
          font-size: 0.6rem;
          text-transform: uppercase;
          padding: 2px 6px;
          border-radius: 4px;
          background: rgba(255, 255, 255, 0.05);
        }
        .status-badge.active {
          color: #00ff00;
          background: rgba(0, 255, 0, 0.1);
          box-shadow: 0 0 50px rgba(0, 255, 0, 0.05);
        }
        .status-badge.idle {
          color: #666;
        }
        .label {
          color: #666;
          font-size: 0.75rem;
        }
        .value {
          font-size: 0.85rem;
          font-weight: 600;
        }
        .nav-controls {
          display: flex;
          gap: 1rem;
        }
      `}</style>
    </div>
  );
}
