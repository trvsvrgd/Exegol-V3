"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface CostMetrics {
  total_spend: number;
  daily_average: number;
  remaining_quota: number;
  cloud_status: "Healthy" | "Degraded" | "Offline";
  provider_breakdown: Record<string, number>;
  agent_costs: Record<string, number>;
}

export default function CostDashboard() {
  const [metrics, setMetrics] = useState<CostMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchCostMetrics = () => {
    // In a real implementation, this would fetch from the Intel Ima agent's API
    // For now, we simulate the data
    setTimeout(() => {
      setMetrics({
        total_spend: 124.50,
        daily_average: 12.45,
        remaining_quota: 875.50,
        cloud_status: "Healthy",
        provider_breakdown: {
          "OpenAI": 85.00,
          "Anthropic": 25.50,
          "Ollama (Local)": 0,
          "AWS Infrastructure": 14.00
        },
        agent_costs: {
          "ArchitectArtooAgent": 45.20,
          "DeveloperDexAgent": 35.80,
          "QualityQuigonAgent": 15.50,
          "IntelImaAgent": 5.00,
          "VibeVaderAgent": 23.00
        }
      });
      setLoading(false);
    }, 1000);
  };

  useEffect(() => {
    fetchCostMetrics();
  }, []);

  if (loading) return <div className="loading">Initializing Cost & Quota Telemetry...</div>;

  return (
    <div className="metrics-page">
      <header className="metrics-header">
        <h1 className="title-glow">Cost & Quota Management</h1>
        <p className="subtitle">Real-time spend tracking and cloud status managed by Intel Ima.</p>
        <div className="nav-controls mt-4">
          <Link href="/" className="btn-outline">Back to Tower</Link>
        </div>
      </header>

      {metrics && (
        <>
          <section className="summary-grid">
            <div className="summary-card glass">
              <span className="label">Total Spend (MTD)</span>
              <span className="value text-red">${metrics.total_spend.toFixed(2)}</span>
            </div>
            <div className="summary-card glass">
              <span className="label">Remaining Quota</span>
              <span className="value success-text">${metrics.remaining_quota.toFixed(2)}</span>
            </div>
            <div className="summary-card glass">
              <span className="label">Cloud Status</span>
              <span className={`value ${metrics.cloud_status === 'Healthy' ? 'success-text' : 'text-red'}`}>{metrics.cloud_status}</span>
            </div>
          </section>

          <section className="sector-grid">
            <div className="sector">
              <h2 className="section-title">Provider Breakdown</h2>
              <div className="metrics-grid">
                {Object.entries(metrics.provider_breakdown).map(([provider, cost]) => (
                  <div key={provider} className="metric-card glass">
                    <div className="card-header">
                      <h3>{provider}</h3>
                    </div>
                    <div className="stats-row">
                      <div className="stat">
                        <span className="stat-label">Cost</span>
                        <span className="stat-value">${cost.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="sector">
              <h2 className="section-title">Agent Cost Breakdown</h2>
              <div className="metrics-grid">
                {Object.entries(metrics.agent_costs).map(([agent, cost]) => (
                  <div key={agent} className="metric-card glass">
                    <div className="card-header">
                      <h3>{agent}</h3>
                    </div>
                    <div className="stats-row">
                      <div className="stat">
                        <span className="stat-label">Spend</span>
                        <span className="stat-value">${cost.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </>
      )}

      <style jsx>{`
        .metrics-page {
          padding: 3rem;
          min-height: 100vh;
          background: linear-gradient(to bottom, #070707, #111111);
          color: #eaeaea;
        }
        .metrics-header {
          margin-bottom: 4rem;
        }
        .subtitle {
          color: var(--text-secondary);
          opacity: 0.7;
          margin-top: 0.5rem;
          font-size: 1.1rem;
        }
        .mt-4 {
          margin-top: 1.5rem;
        }
        .summary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
          gap: 2rem;
          margin-bottom: 4rem;
        }
        .summary-card {
          padding: 2.5rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 16px;
          background: rgba(20, 20, 20, 0.5);
          backdrop-filter: blur(12px);
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        }
        .summary-card .label {
          font-size: 0.8rem;
          text-transform: uppercase;
          letter-spacing: 2px;
          color: var(--text-secondary);
          margin-bottom: 1rem;
        }
        .summary-card .value {
          font-size: 3rem;
          font-weight: 800;
          font-family: 'JetBrains Mono', monospace;
        }
        .success-text { color: #2ecc71; text-shadow: 0 0 25px rgba(46, 204, 113, 0.25); }
        .text-red { color: #ff8787; text-shadow: 0 0 15px rgba(255, 135, 135, 0.3); }
        .section-title {
          font-size: 1rem;
          text-transform: uppercase;
          letter-spacing: 3px;
          color: #888;
          margin-bottom: 2rem;
          padding-left: 1rem;
          border-left: 4px solid #4dabf7;
        }
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 1.5rem;
          margin-bottom: 2rem;
        }
        .metric-card {
          padding: 1.5rem;
          border-radius: 16px;
          background: rgba(25, 25, 25, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          backdrop-filter: blur(10px);
          display: flex;
          flex-direction: column;
        }
        .card-header h3 {
          margin: 0;
          font-size: 1.1rem;
          color: #fff;
          font-weight: 600;
        }
        .stats-row {
          display: flex;
          justify-content: space-between;
          margin-top: 1rem;
        }
        .stat-label {
          font-size: 0.7rem;
          text-transform: uppercase;
          color: #888;
          margin-bottom: 0.25rem;
          display: block;
        }
        .stat-value {
          font-size: 1.3rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
          color: #eee;
        }
        .loading {
          padding: 4rem;
          text-align: center;
          color: #888;
          letter-spacing: 3px;
          text-transform: uppercase;
          font-size: 0.9rem;
          animation: pulse 2s infinite;
        }
        @keyframes pulse {
          0% { opacity: 0.4; }
          50% { opacity: 1; }
          100% { opacity: 0.4; }
        }
        .btn-outline {
          border: 1px solid rgba(255, 255, 255, 0.2);
          background: transparent;
          color: white;
          padding: 0.5rem 1rem;
          border-radius: 6px;
          text-decoration: none;
          font-size: 0.9rem;
          transition: all 0.2s ease;
        }
        .btn-outline:hover {
          background: rgba(255, 255, 255, 0.05);
          border-color: rgba(255, 255, 255, 0.4);
        }
      `}</style>
    </div>
  );
}
