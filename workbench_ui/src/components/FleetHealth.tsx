"use client";

import { useState, useEffect } from "react";

interface HealthMetric {
  name: string;
  path: string;
  status: string;
  priority: number;
  backlog_count: number;
  hitl_count: number;
  last_activity: string | null;
  last_agent: string | null;
  last_outcome: string | null;
}

interface FleetHealthProps {
  onSelect: (path: string) => void;
  activePath: string | null;
}

export default function FleetHealth({ onSelect, activePath }: FleetHealthProps) {
  const [metrics, setMetrics] = useState<HealthMetric[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHealth = () => {
    fetch("http://localhost:8000/fleet/health", {
        headers: { "X-API-Key": "dev-local-key" }
    })
      .then(res => res.json())
      .then(data => {
        setMetrics(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch fleet health:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="loading">Initializing Fleet Telemetry...</div>;

  return (
    <div className="fleet-health-sector">
      <div className="health-grid">
        {metrics.map(metric => (
          <div 
            key={metric.path} 
            className={`health-card glass ${activePath === metric.path ? 'active-border' : ''}`}
            onClick={() => onSelect(metric.path)}
          >
            <div className="card-header">
              <div className="title-group">
                <h3>{metric.name}</h3>
                <span className="repo-path">{metric.path}</span>
              </div>
              <div className={`status-indicator ${metric.status}`}></div>
            </div>

            <div className="stats-row">
              <div className="stat">
                <span className="stat-label">Backlog</span>
                <span className={`stat-value ${metric.backlog_count > 5 ? 'warning' : ''}`}>
                  {metric.backlog_count}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">HITL</span>
                <span className={`stat-value ${metric.hitl_count > 0 ? 'critical' : ''}`}>
                  {metric.hitl_count}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">Priority</span>
                <span className="stat-value">{metric.priority}</span>
              </div>
            </div>

            <div className="activity-footer">
              {metric.last_activity ? (
                <>
                  <div className="activity-main">
                    <span className="agent-tag">{metric.last_agent}</span>
                    <span className={`outcome-dot ${metric.last_outcome}`}></span>
                    <span className="timestamp">
                      {new Date(metric.last_activity).toLocaleTimeString()}
                    </span>
                  </div>
                </>
              ) : (
                <span className="no-activity">No recent activity</span>
              )}
            </div>
          </div>
        ))}
      </div>

      <style jsx>{`
        .fleet-health-sector {
          margin-bottom: 2rem;
        }
        .health-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 1.5rem;
        }
        .health-card {
          padding: 1.5rem;
          border: 1px solid rgba(255, 255, 255, 0.05);
          position: relative;
          overflow: hidden;
          background: rgba(20, 20, 20, 0.4);
          backdrop-filter: blur(10px);
        }
        .health-card::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          width: 4px;
          height: 100%;
          background: var(--accent-color);
          opacity: 0.3;
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 1.5rem;
        }
        .title-group h3 {
          margin: 0;
          font-size: 1.1rem;
          color: var(--text-primary);
          letter-spacing: 0.5px;
        }
        .repo-path {
          font-size: 0.7rem;
          color: var(--text-secondary);
          opacity: 0.6;
          display: block;
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 200px;
        }
        .status-indicator {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          box-shadow: 0 0 10px currentColor;
        }
        .status-indicator.active { color: #00ff00; background: #00ff00; }
        .status-indicator.idle { color: #666; background: #666; }
        .status-indicator.blocked { color: #ff0000; background: #ff0000; }

        .stats-row {
          display: flex;
          gap: 2rem;
          margin-bottom: 1.5rem;
          padding: 1rem 0;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .stat {
          display: flex;
          flex-direction: column;
        }
        .stat-label {
          font-size: 0.65rem;
          text-transform: uppercase;
          color: var(--text-secondary);
          letter-spacing: 1px;
          margin-bottom: 4px;
        }
        .stat-value {
          font-size: 1.2rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
        }
        .stat-value.warning { color: #f39c12; }
        .stat-value.critical { color: #e74c3c; text-shadow: 0 0 10px rgba(231, 76, 60, 0.3); }

        .activity-footer {
          font-size: 0.75rem;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .activity-main {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .agent-tag {
          background: rgba(255, 255, 255, 0.05);
          padding: 2px 8px;
          border-radius: 12px;
          color: var(--accent-color);
          font-weight: 600;
        }
        .outcome-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
        }
        .outcome-dot.success { background: #00ff00; }
        .outcome-dot.failure { background: #ff0000; }
        
        .timestamp {
          color: var(--text-secondary);
          opacity: 0.7;
        }
        .no-activity {
          color: var(--text-secondary);
          font-style: italic;
          opacity: 0.5;
        }
        .loading {
          padding: 2rem;
          text-align: center;
          color: var(--text-secondary);
          letter-spacing: 2px;
          text-transform: uppercase;
          font-size: 0.8rem;
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0% { opacity: 0.5; }
          50% { opacity: 1; }
          100% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}
