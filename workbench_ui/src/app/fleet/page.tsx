"use client";

import { useState, useEffect } from "react";
import FleetHealth from "../../components/FleetHealth";

import { apiGet } from "../api-client";

interface FleetSummary {
  totalRepos: number;
  totalBacklog: number;
  avgSuccessRate: number;
  activeAgents: number;
}

export default function FleetDashboard() {
  const [metrics, setMetrics] = useState<any[]>([]);
  const [summary, setSummary] = useState<FleetSummary>({
    totalRepos: 0,
    totalBacklog: 0,
    avgSuccessRate: 0,
    activeAgents: 0,
  });

  const fetchHealth = async () => {
    try {
      const data = await apiGet<any[]>("/fleet/health");
      setMetrics(data);
      const totalBacklog = data.reduce((acc: number, curr: any) => acc + curr.backlog_count, 0);
      const avgSuccess = data.length > 0 ? data.reduce((acc: number, curr: any) => acc + curr.success_rate, 0) / data.length : 0;
      const activeCount = data.filter((m: any) => m.status === "active").length;
      
      setSummary({
        totalRepos: data.length,
        totalBacklog,
        avgSuccessRate: avgSuccess,
        activeAgents: activeCount,
      });
    } catch (err) {
      console.error("Failed to fetch fleet health:", err);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fleet-page">
      <header className="fleet-header">
        <h1 className="title-glow">Fleet Intelligence Dashboard</h1>
        <p className="subtitle">Real-time telemetry and cross-repository performance analytics.</p>
      </header>

      <section className="summary-grid">
        <div className="summary-card glass">
          <span className="label">Managed Repos</span>
          <span className="value">{summary.totalRepos}</span>
        </div>
        <div className="summary-card glass">
          <span className="label">Total Backlog</span>
          <span className="value">{summary.totalBacklog}</span>
        </div>
        <div className="summary-card glass">
          <span className="label">Avg Success Rate</span>
          <span className="value success-text">{summary.avg_successRate?.toFixed(1) || summary.avgSuccessRate.toFixed(1)}%</span>
        </div>
        <div className="summary-card glass">
          <span className="label">Active Agents</span>
          <span className="value active-text">{summary.activeAgents}</span>
        </div>
      </section>

      <section className="fleet-details">
        <h2 className="section-title">Repository Telemetry</h2>
        <FleetHealth onSelect={() => {}} activePath={null} />
      </section>

      <style jsx>{`
        .fleet-page {
          padding: 3rem;
          min-height: 100vh;
          background: linear-gradient(to bottom, #0a0a0a, #121212);
        }
        .fleet-header {
          margin-bottom: 4rem;
        }
        .subtitle {
          color: var(--text-secondary);
          opacity: 0.7;
          margin-top: 0.5rem;
        }
        .summary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 2rem;
          margin-bottom: 4rem;
        }
        .summary-card {
          padding: 2rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .summary-card .label {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 2px;
          color: var(--text-secondary);
          margin-bottom: 0.5rem;
        }
        .summary-card .value {
          font-size: 2.5rem;
          font-weight: 800;
          font-family: 'JetBrains Mono', monospace;
        }
        .success-text { color: #2ecc71; text-shadow: 0 0 20px rgba(46, 204, 113, 0.2); }
        .active-text { color: #00ff00; text-shadow: 0 0 20px rgba(0, 255, 0, 0.2); }
        
        .section-title {
          font-size: 0.9rem;
          text-transform: uppercase;
          letter-spacing: 3px;
          color: #555;
          margin-bottom: 2rem;
          padding-left: 1rem;
          border-left: 3px solid var(--accent-color);
        }
      `}</style>
    </div>
  );
}
