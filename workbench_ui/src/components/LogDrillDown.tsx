"use client";

import { useState, useEffect } from "react";

interface InteractionLog {
  timestamp: string;
  agent_id: string;
  session_id: string;
  outcome: string;
  task_summary: string;
  steps_used: number;
  duration_seconds: number;
  errors: string[];
  state_changes: Record<string, any>;
  metrics: Record<string, any>;
}

interface LogDrillDownProps {
  isOpen: boolean;
  onClose: () => void;
  repoPath: string;
  apiKey: string;
  apiBaseUrl: string;
  initialAgentId?: string;
  initialOutcome?: string;
}

export default function LogDrillDown({
  isOpen,
  onClose,
  repoPath,
  apiKey,
  apiBaseUrl,
  initialAgentId,
  initialOutcome
}: LogDrillDownProps) {
  const [logs, setLogs] = useState<InteractionLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterAgent, setFilterAgent] = useState(initialAgentId || "");
  const [filterOutcome, setFilterOutcome] = useState(initialOutcome || "");
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [agentProfile, setAgentProfile] = useState<any>(null);

  useEffect(() => {
    if (isOpen) {
      fetchLogs();
    }
  }, [isOpen, filterAgent, filterOutcome]);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      let url = `${apiBaseUrl}/fleet/interactions?repo_path=${encodeURIComponent(repoPath)}`;
      if (filterAgent) url += `&agent_id=${encodeURIComponent(filterAgent)}`;
      if (filterOutcome) url += `&outcome=${encodeURIComponent(filterOutcome)}`;

      const res = await fetch(url, {
        headers: { "X-API-Key": apiKey }
      });
      const data = await res.json();
      
      if (Array.isArray(data)) {
        setLogs(data);
      } else {
        console.error("API returned non-array data:", data);
        setLogs([]);
      }
    } catch (err) {
      console.error("Failed to fetch interaction logs:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAgentProfile = async () => {
    if (!filterAgent) {
      setAgentProfile(null);
      return;
    }
    try {
      const res = await fetch(`${apiBaseUrl}/agents`, {
        headers: { "X-API-Key": apiKey }
      });
      const data = await res.json();
      const profile = data.find((a: any) => a.id === filterAgent);
      setAgentProfile(profile);
    } catch (err) {
      console.error("Failed to fetch agent profile:", err);
    }
  };

  useEffect(() => {
    if (isOpen && filterAgent) {
      fetchAgentProfile();
    }
  }, [isOpen, filterAgent]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content glass" onClick={e => e.stopPropagation()}>
        <header className="modal-header">
          <div className="header-titles">
            <h2>Interaction Drill-Down</h2>
            <p className="subtitle">Analyzing telemetry for {filterAgent || "All Agents"}</p>
          </div>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </header>

        <div className="filters-bar">
          <div className="filter-group">
            <label>Outcome</label>
            <select value={filterOutcome} onChange={e => setFilterOutcome(e.target.value)}>
              <option value="">All Outcomes</option>
              <option value="success">Success</option>
              <option value="failure">Failure</option>
              <option value="partial">Partial</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Agent</label>
            <input 
              type="text" 
              placeholder="Filter by agent id..." 
              value={filterAgent} 
              onChange={e => setFilterAgent(e.target.value)}
            />
          </div>
          <button className="refresh-btn" onClick={fetchLogs} disabled={loading}>
            {loading ? "..." : "Refresh"}
          </button>
        </div>

        {agentProfile && (
          <div className="agent-profile-section">
            <div className="profile-header">
              <h3>{agentProfile.name} Profile</h3>
              <span className="wake-word">Wake Word: "{agentProfile.wake_word}"</span>
            </div>
            <div className="profile-tools">
              <h4>Accessible Tools</h4>
              <div className="tool-tags">
                {agentProfile.tools.map((tool: any) => (
                  <div key={tool.id} className="tool-tag-detailed glass">
                    <span className="tool-name">{tool.id}</span>
                    <span className="tool-risk" style={{ color: tool.risk === 'critical' ? '#ff4757' : tool.risk === 'high' ? '#ffa502' : '#2ed573' }}>
                      {tool.risk}
                    </span>
                    <p className="tool-desc">{tool.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="logs-container">
          {loading && <div className="loading-state">Syncing telemetry...</div>}
          {!loading && (!Array.isArray(logs) || logs.length === 0) && <div className="empty-state">No logs found for the current filters.</div>}
          
          {Array.isArray(logs) && logs.map((log) => (
            <div key={log.session_id + log.timestamp} className={`log-item ${expandedLog === log.session_id ? 'expanded' : ''}`}>
              <div className="log-summary" onClick={() => setExpandedLog(expandedLog === log.session_id ? null : log.session_id)}>
                <div className="log-meta">
                  <span className="timestamp">{new Date(log.timestamp).toLocaleString()}</span>
                  <span className={`outcome-badge ${log.outcome}`}>{log.outcome}</span>
                </div>
                <div className="log-title">
                  <span className="agent-tag">{log.agent_id}</span>
                  <span className="summary-text">{log.task_summary}</span>
                </div>
                <div className="log-stats">
                  <span>{log.steps_used} steps</span>
                  <span>{log.duration_seconds}s</span>
                </div>
              </div>

              {expandedLog === log.session_id && (
                <div className="log-details">
                  {log.errors.length > 0 && (
                    <div className="detail-section errors">
                      <h4>Errors Detected</h4>
                      <ul>
                        {log.errors.map((err, i) => <li key={i}>{err}</li>)}
                      </ul>
                    </div>
                  )}
                  
                  <div className="detail-grid">
                    <div className="detail-section">
                      <h4>State Changes</h4>
                      <pre>{JSON.stringify(log.state_changes, null, 2)}</pre>
                    </div>
                    <div className="detail-section">
                      <h4>Performance Metrics</h4>
                      <pre>{JSON.stringify(log.metrics, null, 2)}</pre>
                    </div>
                  </div>
                  
                  <div className="detail-section">
                    <h4>Session ID</h4>
                    <code>{log.session_id}</code>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <style jsx>{`
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.85);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 2rem;
        }
        .modal-content {
          width: 100%;
          max-width: 1000px;
          max-height: 85vh;
          background: #0f0f0f;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 20px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .modal-header {
          padding: 1.5rem 2rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .header-titles h2 {
          margin: 0;
          font-size: 1.5rem;
          color: #fff;
          letter-spacing: 1px;
        }
        .subtitle {
          margin: 0.25rem 0 0 0;
          font-size: 0.9rem;
          color: #888;
        }
        .close-btn {
          background: none;
          border: none;
          color: #888;
          font-size: 2rem;
          cursor: pointer;
          line-height: 1;
          transition: color 0.2s;
        }
        .close-btn:hover { color: #fff; }

        .filters-bar {
          padding: 1rem 2rem;
          display: flex;
          gap: 1.5rem;
          background: rgba(255, 255, 255, 0.02);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          align-items: flex-end;
        }
        .filter-group {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .filter-group label {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #555;
        }
        .filters-bar select, .filters-bar input {
          background: #1a1a1a;
          border: 1px solid #333;
          color: #eee;
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
          font-size: 0.9rem;
        }
        .refresh-btn {
          background: #4dabf7;
          color: #fff;
          border: none;
          padding: 0.5rem 1.25rem;
          border-radius: 6px;
          cursor: pointer;
          font-weight: 600;
          transition: background 0.2s;
        }
        .refresh-btn:hover { background: #339af0; }

        .logs-container {
          flex: 1;
          overflow-y: auto;
          padding: 1rem 2rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .log-item {
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 10px;
          overflow: hidden;
          background: rgba(255, 255, 255, 0.01);
          transition: all 0.2s;
        }
        .log-item:hover {
          border-color: rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.03);
        }
        .log-summary {
          padding: 1rem;
          cursor: pointer;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .log-meta {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .timestamp { font-size: 0.75rem; color: #666; font-family: 'JetBrains Mono', monospace; }
        .outcome-badge {
          font-size: 0.65rem;
          text-transform: uppercase;
          padding: 2px 8px;
          border-radius: 10px;
          font-weight: 700;
        }
        .outcome-badge.success { background: rgba(46, 204, 113, 0.2); color: #2ecc71; }
        .outcome-badge.failure { background: rgba(231, 76, 60, 0.2); color: #e74c3c; }
        .outcome-badge.partial { background: rgba(241, 196, 15, 0.2); color: #f1c40f; }

        .log-title {
          display: flex;
          gap: 0.75rem;
          align-items: center;
        }
        .agent-tag {
          font-size: 0.8rem;
          font-weight: 700;
          color: #4dabf7;
          background: rgba(77, 171, 247, 0.1);
          padding: 2px 6px;
          border-radius: 4px;
        }
        .summary-text {
          font-size: 0.95rem;
          color: #eee;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .log-stats {
          display: flex;
          gap: 1rem;
          font-size: 0.75rem;
          color: #666;
        }

        .log-details {
          padding: 1.5rem;
          background: rgba(0, 0, 0, 0.3);
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }
        .detail-section h4 {
          margin: 0 0 0.75rem 0;
          font-size: 0.8rem;
          text-transform: uppercase;
          color: #888;
          letter-spacing: 1px;
        }
        .detail-section pre {
          background: #000;
          padding: 1rem;
          border-radius: 8px;
          font-size: 0.8rem;
          font-family: 'JetBrains Mono', monospace;
          color: #10b981;
          overflow-x: auto;
          margin: 0;
        }
        .detail-section ul {
          margin: 0;
          padding-left: 1.25rem;
          color: #ff8787;
          font-size: 0.9rem;
        }
        .detail-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1.5rem;
        }
        .loading-state, .empty-state {
          padding: 4rem;
          text-align: center;
          color: #555;
          font-style: italic;
        }

        .agent-profile-section {
          padding: 1.5rem 2rem;
          background: rgba(77, 171, 247, 0.05);
          border-bottom: 1px solid rgba(77, 171, 247, 0.1);
        }
        .profile-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .profile-header h3 { margin: 0; color: #4dabf7; font-size: 1.1rem; }
        .wake-word { font-size: 0.8rem; color: #888; font-style: italic; }
        
        .profile-tools h4 {
          font-size: 0.7rem;
          text-transform: uppercase;
          color: #555;
          margin-bottom: 0.75rem;
          letter-spacing: 1px;
        }
        .tool-tags {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 1rem;
        }
        .tool-tag-detailed {
          padding: 0.75rem;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .tool-name { font-weight: 700; color: #eee; font-size: 0.85rem; display: block; margin-bottom: 0.25rem; }
        .tool-risk { font-size: 0.6rem; text-transform: uppercase; font-weight: 800; display: block; margin-bottom: 0.5rem; }
        .tool-desc { font-size: 0.75rem; color: #888; line-height: 1.4; margin: 0; }
      `}</style>
    </div>
  );
}
