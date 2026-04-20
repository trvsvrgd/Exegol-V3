"use client";

import { useState, useEffect } from "react";

interface Repo {
  repo_path: string;
  model_routing_preference: string;
  priority: number;
  agent_status: string;
}

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);

  useEffect(() => {
    fetch("http://localhost:8000/repos")
      .then(res => res.json())
      .then(data => setRepos(data))
      .catch(err => console.error("Failed to fetch repos:", err));
  }, []);

  return (
    <div className="container">
      <header style={{ marginBottom: '3rem' }}>
        <h1 className="title-glow">Fleet Command</h1>
        <p style={{ color: '#888' }}>Monitoring all active sectors of the project ecosystem.</p>
      </header>

      <div className="repo-grid">
        {repos.map(repo => (
          <div key={repo.repo_path} className="glass repo-card">
            <div className="repo-header">
              <h3>{repo.repo_path.split('\\').pop()}</h3>
              <span className={`status-badge ${repo.agent_status}`}>
                {repo.agent_status}
              </span>
            </div>
            <div className="repo-details">
              <div className="detail">
                <span className="label">Current Brain:</span>
                <span className="value title-glow">{repo.model_routing_preference.toUpperCase()}</span>
              </div>
              <div className="detail">
                <span className="label">Priority:</span>
                <span className="value">Level {repo.priority}</span>
              </div>
            </div>
            <div className="repo-actions">
              <a href="/ab-test" className="btn-outline" style={{ display: 'block', textAlign: 'center', fontSize: '0.8rem' }}>
                Open A/B Lab
              </a>
            </div>
          </div>
        ))}
      </div>

      <style jsx>{`
        .repo-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 2rem;
        }
        .repo-card {
          padding: 1.5rem;
          transition: transform 0.3s ease;
        }
        .repo-card:hover {
          transform: translateY(-5px);
          border-color: var(--accent-color);
        }
        .repo-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
        }
        .status-badge {
          font-size: 0.7rem;
          text-transform: uppercase;
          padding: 4px 8px;
          border-radius: 4px;
          background: rgba(255, 255, 255, 0.1);
        }
        .status-badge.active {
          color: #00ff00;
          background: rgba(0, 255, 0, 0.1);
        }
        .status-badge.idle {
          color: #888;
        }
        .repo-details {
          margin-bottom: 1.5rem;
        }
        .detail {
          display: flex;
          justify-content: space-between;
          margin-bottom: 0.5rem;
          font-size: 0.9rem;
        }
        .label {
          color: #777;
        }
        .value {
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
