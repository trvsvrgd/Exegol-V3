"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { apiGet, getLocalActiveRepo, setLocalActiveRepo } from "../api-client";

interface Repo {
  repo_path: string;
  model_routing_preference: string;
  priority: number;
  agent_status: string;
}

interface EvalRequirement {
  id: string;
  technique_name: string;
  category: string;
  source_url: string;
  description: string;
  priority: string;
  status: string;
  added_date: string;
  added_by: string;
}

interface EvalReport {
  generated_at: string;
  techniques_researched: number;
  new_techniques_added: number;
  stale_requirements_flagged: number;
  total_requirements: number;
  new_requirements: EvalRequirement[];
  stale_requirements: string[];
}

export default function EvaluationsDashboard() {
  const [reports, setReports] = useState<string[]>([]);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
  const [reportData, setReportData] = useState<EvalReport | null>(null);

  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string>("");

  // Load repositories and initial active repo
  useEffect(() => {
    async function loadRepos() {
      try {
        const repoList = await apiGet<Repo[]>("/repos");
        setRepos(Array.isArray(repoList) ? repoList : []);

        const saved = getLocalActiveRepo();
        if (saved && repoList.some((r) => r.repo_path === saved)) {
          setActiveRepo(saved);
        } else if (repoList.length > 0) {
          setActiveRepo(repoList[0].repo_path);
          setLocalActiveRepo(repoList[0].repo_path);
        } else {
          if (saved) setActiveRepo(saved);
        }
      } catch (err) {
        console.error("Failed to load repositories:", err);
        const saved = getLocalActiveRepo();
        if (saved) setActiveRepo(saved);
      }
    }
    loadRepos();
  }, []);

  useEffect(() => {
    if (!activeRepo) return;
    apiGet<string[]>(`/evaluations?repo_path=${encodeURIComponent(activeRepo)}`)
      .then(data => {
        const arr = Array.isArray(data) ? data : [];
        setReports(arr);
        if (arr.length > 0) {
          setSelectedReport(arr[0]);
        } else {
          setSelectedReport(null);
          setReportData(null);
        }
      })
      .catch(err => {
        console.error("Failed to fetch evaluation reports:", err);
        setReports([]);
        setSelectedReport(null);
        setReportData(null);
      });
  }, [activeRepo]);

  useEffect(() => {
    if (selectedReport && activeRepo) {
      apiGet<EvalReport>(`/evaluations/${selectedReport}?repo_path=${encodeURIComponent(activeRepo)}`)
        .then(data => setReportData(data))
        .catch(err => {
          console.error("Failed to fetch report data:", err);
          setReportData(null);
        });
    }
  }, [selectedReport, activeRepo]);

  return (
    <div className="evaluations-page">
      <header className="evaluations-header">
        <div className="header-left">
          <h1 className="title-glow">Evaluations & LLM-as-a-Judge Reports</h1>
          <p className="subtitle">Review qualitative evaluations, new testing requirements, and agent drift analysis.</p>
        </div>
        <div className="header-actions">
          <select
            id="repo-selector"
            value={activeRepo}
            onChange={(e) => {
              const val = e.target.value;
              setActiveRepo(val);
              setLocalActiveRepo(val);
            }}
            className="period-select"
            style={{ minWidth: "160px" }}
            aria-label="Select active repository"
          >
            {repos.length > 0 ? (
              repos.map((r) => {
                const pathParts = r.repo_path.split(/[/\\]/).filter(Boolean);
                const label = pathParts.slice(-1)[0];
                return (
                  <option key={r.repo_path} value={r.repo_path}>
                    {label}
                  </option>
                );
              })
            ) : (
              activeRepo && (
                <option value={activeRepo}>
                  {activeRepo.split(/[/\\]/).filter(Boolean).slice(-1)[0] || activeRepo}
                </option>
              )
            )}
          </select>
          <Link href="/" className="btn-outline" id="back-to-tower">
            ← Tower
          </Link>
        </div>
      </header>

      <div className="evaluations-layout">
        <aside className="reports-sidebar glass">
          <h2 className="sidebar-title">Recent Reports</h2>
          <div className="reports-list">
            {(reports || []).map((report) => (
              <div 
                key={report} 
                className={`report-item ${selectedReport === report ? 'active' : ''}`}
                onClick={() => setSelectedReport(report)}
              >
                <div className="report-icon">📊</div>
                <div className="report-name">{report.replace('.json', '')}</div>
              </div>
            ))}
            {(reports || []).length === 0 && (
              <div className="no-reports">No reports available</div>
            )}
          </div>
        </aside>

        <main className="report-content">
          {reportData ? (
            <div className="report-details animation-fade-in">
              <div className="stats-grid">
                <div className="stat-card glass">
                  <span className="stat-label">Techniques Researched</span>
                  <span className="stat-value text-blue">{reportData.techniques_researched ?? 0}</span>
                </div>
                <div className="stat-card glass">
                  <span className="stat-label">New Requirements</span>
                  <span className="stat-value text-green">{reportData.new_techniques_added ?? 0}</span>
                </div>
                <div className="stat-card glass">
                  <span className="stat-label">Total Requirements</span>
                  <span className="stat-value">{reportData.total_requirements ?? 0}</span>
                </div>
                <div className="stat-card glass">
                  <span className="stat-label">Stale Flagged</span>
                  <span className="stat-value text-red">{reportData.stale_requirements_flagged ?? 0}</span>
                </div>
              </div>

              <h3 className="section-heading">New Evaluation Requirements</h3>
              <div className="requirements-list">
                {(reportData.new_requirements || []).length > 0 ? (reportData.new_requirements || []).map(req => (
                  <div key={req.id} className="requirement-card glass">
                    <div className="req-header">
                      <h4>{req.technique_name}</h4>
                      <span className={`priority-badge ${req.priority}`}>{req.priority}</span>
                    </div>
                    <div className="req-meta">
                      <span><strong>Category:</strong> {req.category}</span>
                      <span><strong>Added By:</strong> {req.added_by}</span>
                    </div>
                    <p className="req-description">{req.description}</p>
                    <a href={req.source_url} target="_blank" rel="noopener noreferrer" className="req-link">View Source Document ↗</a>
                  </div>
                )) : (
                  <div className="no-data">No new requirements added in this report.</div>
                )}
              </div>
            </div>
          ) : (
            <div className="loading-state">Select a report to view details...</div>
          )}
        </main>
      </div>

      <style jsx>{`
        .evaluations-page {
          padding: 2.5rem;
          min-height: 100vh;
          background: linear-gradient(to bottom, #050505, #0f0f0f);
          color: #eaeaea;
        }
        .evaluations-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 2rem;
          margin-bottom: 2.5rem;
          flex-wrap: wrap;
        }
        .header-actions {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          flex-wrap: wrap;
        }
        .period-select {
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.12);
          color: #ccc;
          padding: 0.5rem 0.85rem;
          border-radius: 8px;
          font-size: 0.85rem;
          cursor: pointer;
          outline: none;
        }
        .period-select:hover { border-color: rgba(255,255,255,0.25); }
        .btn-outline {
          border: 1px solid rgba(255,255,255,0.15);
          background: transparent;
          color: #aaa;
          padding: 0.5rem 1rem;
          border-radius: 8px;
          text-decoration: none;
          font-size: 0.85rem;
          transition: all 0.2s ease;
        }
        .btn-outline:hover { color: #fff; border-color: rgba(255,255,255,0.3); }
        .subtitle {
          color: #a0a0a0;
          font-size: 1rem;
          margin-top: 0.5rem;
        }
        .evaluations-layout {
          display: grid;
          grid-template-columns: 300px 1fr;
          gap: 2rem;
          height: calc(100vh - 150px);
        }
        .reports-sidebar {
          padding: 1.5rem;
          border-radius: 12px;
          border: 1px solid rgba(255, 255, 255, 0.08);
          overflow-y: auto;
          background: rgba(20, 20, 20, 0.6);
          backdrop-filter: blur(10px);
        }
        .sidebar-title {
          font-size: 0.85rem;
          text-transform: uppercase;
          letter-spacing: 2px;
          color: #888;
          margin-bottom: 1.5rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          padding-bottom: 0.75rem;
        }
        .reports-list {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .report-item {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 1rem;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          border: 1px solid transparent;
          background: rgba(255, 255, 255, 0.02);
        }
        .report-item:hover {
          background: rgba(255, 255, 255, 0.05);
          transform: translateX(4px);
        }
        .report-item.active {
          background: rgba(0, 150, 255, 0.1);
          border-color: rgba(0, 150, 255, 0.3);
          box-shadow: inset 4px 0 0 #0096ff;
        }
        .report-name {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .report-content {
          overflow-y: auto;
          padding-right: 1rem;
        }
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 1.5rem;
          margin-bottom: 3rem;
        }
        .stat-card {
          padding: 1.5rem;
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          background: rgba(20, 20, 20, 0.4);
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }
        .stat-label {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #aaa;
          margin-bottom: 0.75rem;
        }
        .stat-value {
          font-size: 2.5rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
        }
        .text-blue { color: #4dabf7; text-shadow: 0 0 15px rgba(77, 171, 247, 0.3); }
        .text-green { color: #69db7c; text-shadow: 0 0 15px rgba(105, 219, 124, 0.3); }
        .text-red { color: #ff8787; text-shadow: 0 0 15px rgba(255, 135, 135, 0.3); }
        
        .section-heading {
          font-size: 1.1rem;
          color: #e0e0e0;
          margin-bottom: 1.5rem;
          padding-bottom: 0.5rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .requirements-list {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }
        .requirement-card {
          padding: 1.5rem;
          border-radius: 10px;
          background: rgba(30, 30, 35, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.05);
          transition: transform 0.2s ease;
        }
        .requirement-card:hover {
          border-color: rgba(255, 255, 255, 0.15);
        }
        .req-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .req-header h4 {
          margin: 0;
          font-size: 1.2rem;
          color: #fff;
        }
        .priority-badge {
          font-size: 0.7rem;
          text-transform: uppercase;
          padding: 4px 8px;
          border-radius: 4px;
          font-weight: 600;
        }
        .priority-badge.high { background: rgba(255, 80, 80, 0.2); color: #ff6b6b; border: 1px solid rgba(255, 80, 80, 0.3); }
        .priority-badge.medium { background: rgba(255, 180, 50, 0.2); color: #fcc419; border: 1px solid rgba(255, 180, 50, 0.3); }
        .priority-badge.low { background: rgba(80, 200, 80, 0.2); color: #51cf66; border: 1px solid rgba(80, 200, 80, 0.3); }
        
        .req-meta {
          display: flex;
          gap: 2rem;
          margin-bottom: 1rem;
          font-size: 0.85rem;
          color: #aaa;
        }
        .req-description {
          line-height: 1.6;
          color: #ccc;
          margin-bottom: 1.2rem;
        }
        .req-link {
          display: inline-block;
          font-size: 0.85rem;
          color: #4dabf7;
          text-decoration: none;
          transition: color 0.2s;
        }
        .req-link:hover {
          color: #74c0fc;
          text-decoration: underline;
        }
        .loading-state, .no-reports, .no-data {
          color: #777;
          font-style: italic;
          text-align: center;
          padding: 2rem;
        }
        .animation-fade-in {
          animation: fadeIn 0.4s ease-out;
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
