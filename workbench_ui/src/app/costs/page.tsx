"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { apiGet } from "../api-client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DailyTrendPoint {
  date: string;
  cost: number;
}

interface CostReport {
  total_spend: number;
  daily_average: number;
  remaining_quota: number;
  monthly_budget: number;
  days_until_budget: number | null;
  cloud_status: "Healthy" | "Near Limit" | "Over Budget";
  agent_costs: Record<string, number>;
  provider_breakdown: Record<string, number>;
  step_breakdown: Record<string, number>;
  session_breakdown: Record<string, number>;
  daily_trend: DailyTrendPoint[];
  period_days: number;
  total_sessions: number;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusColor(status: string) {
  if (status === "Healthy") return "#2ecc71";
  if (status === "Near Limit") return "#f39c12";
  return "#e74c3c";
}

function statusGlow(status: string) {
  if (status === "Healthy") return "0 0 24px rgba(46,204,113,0.3)";
  if (status === "Near Limit") return "0 0 24px rgba(243,156,18,0.3)";
  return "0 0 24px rgba(231,76,60,0.4)";
}

function usd(val: number) {
  return `$${val.toFixed(val < 0.01 && val > 0 ? 4 : 2)}`;
}

// Provider icon hint
const PROVIDER_ICONS: Record<string, string> = {
  "Google (Gemini)": "🌐",
  "OpenAI": "🤖",
  "Anthropic": "🧠",
  "Ollama (Local)": "💻",
  "Other / Unknown": "❓",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SpendBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div style={{ marginTop: "0.75rem", height: "6px", borderRadius: "4px", background: "rgba(255,255,255,0.07)", overflow: "hidden" }}>
      <div
        style={{
          height: "100%",
          width: `${pct}%`,
          background: `linear-gradient(90deg, ${color}cc, ${color})`,
          borderRadius: "4px",
          transition: "width 0.8s cubic-bezier(0.4,0,0.2,1)",
        }}
      />
    </div>
  );
}

function TrendChart({ trend }: { trend: DailyTrendPoint[] }) {
  if (!trend || trend.length === 0) {
    return (
      <div style={{ padding: "2rem", textAlign: "center", color: "#555", fontSize: "0.85rem" }}>
        No spend data logged yet for this period.
      </div>
    );
  }

  const maxCost = Math.max(...trend.map((d) => d.cost), 0.0001);
  const chartH = 80;

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: "4px", height: `${chartH + 24}px`, padding: "0.5rem 0" }}>
      {trend.map((point) => {
        const barH = Math.max((point.cost / maxCost) * chartH, 2);
        const opacity = point.cost > 0 ? 0.85 : 0.2;
        return (
          <div
            key={point.date}
            title={`${point.date}: ${usd(point.cost)}`}
            style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}
          >
            <div
              style={{
                width: "100%",
                height: `${barH}px`,
                background: `rgba(77,171,247,${opacity})`,
                borderRadius: "3px 3px 0 0",
                transition: "height 0.5s ease",
                cursor: "default",
              }}
            />
            <span style={{ fontSize: "0.55rem", color: "#555", writingMode: "vertical-rl", transform: "rotate(180deg)", whiteSpace: "nowrap" }}>
              {point.date.slice(5)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CostDashboard() {
  const [report, setReport] = useState<CostReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  // Read repo_path from localStorage (set by Control Tower page)
  const repoPath =
    typeof window !== "undefined"
      ? localStorage.getItem("exegol_repo_path") ||
        "c:\\Users\\travi\\Documents\\Python_Projects\\Exegol_v3"
      : "c:\\Users\\travi\\Documents\\Python_Projects\\Exegol_v3";

  const fetchCosts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<CostReport>(
        `/costs?repo_path=${encodeURIComponent(repoPath)}&days=${days}`
      );
      setReport(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Failed to load cost data: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [repoPath, days]);

  useEffect(() => {
    fetchCosts();
  }, [fetchCosts]);

  const topAgentMax = report
    ? Math.max(...Object.values(report.agent_costs), 0.0001)
    : 1;

  return (
    <div className="costs-page">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <header className="costs-header">
        <div className="header-left">
          <h1 className="page-title">
            <span className="title-icon">💰</span>
            Cost &amp; Quota Management
          </h1>
          <p className="subtitle">
            Live spend tracking across the fleet · powered by{" "}
            <span className="agent-name">Intel Ima</span>
          </p>
        </div>
        <div className="header-actions">
          <select
            id="period-selector"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="period-select"
            aria-label="Select analysis period"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button id="refresh-costs" onClick={fetchCosts} className="btn-refresh" aria-label="Refresh cost data">
            ↺ Refresh
          </button>
          <Link href="/" className="btn-outline" id="back-to-tower">
            ← Tower
          </Link>
        </div>
      </header>

      {/* ── States ──────────────────────────────────────────────────────── */}
      {loading && (
        <div className="loading-state">
          <div className="spinner" />
          <p>Analyzing fleet spend data…</p>
        </div>
      )}

      {error && !loading && (
        <div className="error-banner">
          <span className="error-icon">⚠</span>
          {error}
          <button onClick={fetchCosts} className="btn-retry">Retry</button>
        </div>
      )}

      {/* ── Main content ──────────────────────────────────────────────── */}
      {report && !loading && (
        <>
          {/* KPI row */}
          <section className="kpi-grid" aria-label="Key cost indicators">
            <div className="kpi-card">
              <span className="kpi-label">Total Spend (MTD)</span>
              <span className="kpi-value spend">{usd(report.total_spend)}</span>
              <span className="kpi-sub">{report.total_sessions} sessions · {report.period_days}d window</span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Daily Average</span>
              <span className="kpi-value neutral">{usd(report.daily_average)}</span>
              <span className="kpi-sub">per day</span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Remaining Budget</span>
              <span className="kpi-value quota">{usd(report.remaining_quota)}</span>
              <span className="kpi-sub">of {usd(report.monthly_budget)} budget</span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Cloud Status</span>
              <span
                className="kpi-value status-val"
                style={{
                  color: statusColor(report.cloud_status),
                  textShadow: statusGlow(report.cloud_status),
                }}
              >
                {report.cloud_status}
              </span>
              {report.days_until_budget !== null && (
                <span className="kpi-sub">~{report.days_until_budget}d until limit</span>
              )}
            </div>
          </section>

          {/* Budget progress bar */}
          <section className="budget-bar-section glass-card" aria-label="Budget utilization">
            <div className="budget-bar-header">
              <span className="section-label">Budget Utilization</span>
              <span className="budget-pct">
                {report.monthly_budget > 0
                  ? `${Math.min(100, (report.total_spend / report.monthly_budget) * 100).toFixed(1)}%`
                  : "—"}
              </span>
            </div>
            <div className="budget-bar-track">
              <div
                className="budget-bar-fill"
                style={{
                  width: `${Math.min(100, (report.total_spend / report.monthly_budget) * 100)}%`,
                  background:
                    report.cloud_status === "Healthy"
                      ? "linear-gradient(90deg, #2ecc71aa, #2ecc71)"
                      : report.cloud_status === "Near Limit"
                      ? "linear-gradient(90deg, #f39c12aa, #f39c12)"
                      : "linear-gradient(90deg, #e74c3caa, #e74c3c)",
                }}
              />
            </div>
          </section>

          {/* Two column: trend + provider */}
          <div className="two-col">
            {/* Daily trend */}
            <section className="glass-card" aria-label="Daily spend trend">
              <h2 className="section-title">Daily Spend Trend</h2>
              <TrendChart trend={report.daily_trend} />
            </section>

            {/* Provider breakdown */}
            <section className="glass-card" aria-label="Provider cost breakdown">
              <h2 className="section-title">By Provider</h2>
              {Object.keys(report.provider_breakdown).length === 0 ? (
                <p className="empty-msg">No provider data yet.</p>
              ) : (
                <div className="provider-list">
                  {Object.entries(report.provider_breakdown)
                    .sort(([, a], [, b]) => b - a)
                    .map(([provider, cost]) => (
                      <div key={provider} className="provider-row">
                        <span className="provider-name">
                          {PROVIDER_ICONS[provider] ?? "🔲"} {provider}
                        </span>
                        <span className="provider-cost">{usd(cost)}</span>
                        <SpendBar
                          value={cost}
                          max={Math.max(...Object.values(report.provider_breakdown))}
                          color="#4dabf7"
                        />
                      </div>
                    ))}
                </div>
              )}
            </section>
          </div>

          {/* Agent cost breakdown */}
          <section className="glass-card" aria-label="Agent cost breakdown">
            <h2 className="section-title">Agent Cost Breakdown</h2>
            {Object.keys(report.agent_costs).length === 0 ? (
              <p className="empty-msg">No interaction logs found for this period. Run some agents first!</p>
            ) : (
              <div className="agent-grid">
                {Object.entries(report.agent_costs)
                  .sort(([, a], [, b]) => b - a)
                  .map(([agentId, cost]) => (
                    <div key={agentId} className="agent-card glass">
                      <div className="agent-card-header">
                        <span className="agent-id">{agentId}</span>
                        <span className="agent-cost-badge">{usd(cost)}</span>
                      </div>
                      <div className="agent-meta">
                        <span>📦 {report.step_breakdown[agentId] ?? 0} steps</span>
                        <span>🔁 {report.session_breakdown[agentId] ?? 0} sessions</span>
                      </div>
                      <SpendBar value={cost} max={topAgentMax} color="#cc5de8" />
                    </div>
                  ))}
              </div>
            )}
          </section>

          <p className="generated-at">
            Report generated at {new Date(report.generated_at).toLocaleString()} ·{" "}
            <button onClick={fetchCosts} className="link-btn">Refresh</button>
          </p>
        </>
      )}

      <style jsx>{`
        .costs-page {
          padding: 2.5rem 3rem;
          min-height: 100vh;
          background: linear-gradient(160deg, #060608 0%, #0d0d12 60%, #080810 100%);
          color: #e8e8f0;
          font-family: 'Inter', 'Segoe UI', sans-serif;
        }

        /* ── Header ── */
        .costs-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 2rem;
          margin-bottom: 3rem;
          flex-wrap: wrap;
        }
        .page-title {
          font-size: 2rem;
          font-weight: 800;
          margin: 0 0 0.4rem;
          background: linear-gradient(135deg, #fff 30%, #4dabf7 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          letter-spacing: -0.5px;
        }
        .title-icon { margin-right: 0.5rem; }
        .subtitle {
          color: #666;
          font-size: 0.95rem;
          margin: 0;
        }
        .agent-name {
          color: #4dabf7;
          font-weight: 600;
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
        .btn-refresh {
          background: rgba(77,171,247,0.12);
          border: 1px solid rgba(77,171,247,0.3);
          color: #4dabf7;
          padding: 0.5rem 1rem;
          border-radius: 8px;
          font-size: 0.85rem;
          cursor: pointer;
          transition: all 0.2s ease;
        }
        .btn-refresh:hover { background: rgba(77,171,247,0.22); }
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

        /* ── States ── */
        .loading-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1.5rem;
          padding: 6rem 0;
          color: #555;
          font-size: 0.9rem;
          letter-spacing: 0.05em;
        }
        .spinner {
          width: 36px; height: 36px;
          border: 3px solid rgba(77,171,247,0.15);
          border-top-color: #4dabf7;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .error-banner {
          display: flex;
          align-items: center;
          gap: 1rem;
          background: rgba(231,76,60,0.1);
          border: 1px solid rgba(231,76,60,0.3);
          border-radius: 12px;
          padding: 1.25rem 1.5rem;
          color: #e74c3c;
          margin-bottom: 2rem;
          font-size: 0.9rem;
        }
        .error-icon { font-size: 1.2rem; }
        .btn-retry {
          margin-left: auto;
          background: rgba(231,76,60,0.15);
          border: 1px solid rgba(231,76,60,0.3);
          color: #e74c3c;
          padding: 0.4rem 0.9rem;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.82rem;
        }

        /* ── KPI grid ── */
        .kpi-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 1.5rem;
          margin-bottom: 2rem;
        }
        .kpi-card {
          background: rgba(18,18,26,0.7);
          border: 1px solid rgba(255,255,255,0.07);
          border-radius: 16px;
          padding: 2rem 1.75rem;
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          backdrop-filter: blur(14px);
          box-shadow: 0 4px 24px rgba(0,0,0,0.3);
          transition: transform 0.2s ease;
        }
        .kpi-card:hover { transform: translateY(-2px); }
        .kpi-label {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 2.5px;
          color: #555;
          margin-bottom: 0.75rem;
        }
        .kpi-value {
          font-size: 2.4rem;
          font-weight: 800;
          font-family: 'JetBrains Mono', 'Fira Code', monospace;
          line-height: 1;
          margin-bottom: 0.5rem;
        }
        .kpi-value.spend   { color: #ff8787; text-shadow: 0 0 20px rgba(255,135,135,0.3); }
        .kpi-value.neutral { color: #e8e8f0; }
        .kpi-value.quota   { color: #2ecc71; text-shadow: 0 0 20px rgba(46,204,113,0.3); }
        .kpi-value.status-val { font-size: 1.6rem; }
        .kpi-sub {
          font-size: 0.72rem;
          color: #444;
        }

        /* ── Budget bar ── */
        .budget-bar-section {
          margin-bottom: 2rem;
          padding: 1.5rem 2rem;
        }
        .budget-bar-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1rem;
        }
        .budget-bar-track {
          height: 8px;
          background: rgba(255,255,255,0.07);
          border-radius: 6px;
          overflow: hidden;
        }
        .budget-bar-fill {
          height: 100%;
          border-radius: 6px;
          transition: width 1s cubic-bezier(0.4,0,0.2,1);
        }
        .budget-pct {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.9rem;
          color: #aaa;
        }

        /* ── Glass card ── */
        .glass-card {
          background: rgba(18,18,26,0.6);
          border: 1px solid rgba(255,255,255,0.07);
          border-radius: 16px;
          padding: 2rem;
          backdrop-filter: blur(14px);
          box-shadow: 0 4px 24px rgba(0,0,0,0.25);
          margin-bottom: 2rem;
        }
        .section-label {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 2px;
          color: #555;
        }
        .section-title {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 3px;
          color: #555;
          margin: 0 0 1.5rem;
          padding-left: 0.75rem;
          border-left: 3px solid #4dabf7;
        }

        /* ── Two column ── */
        .two-col {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 2rem;
          margin-bottom: 2rem;
        }
        @media (max-width: 900px) {
          .two-col { grid-template-columns: 1fr; }
        }

        /* ── Provider list ── */
        .provider-list { display: flex; flex-direction: column; gap: 1.25rem; }
        .provider-row { display: flex; flex-direction: column; }
        .provider-name { font-size: 0.9rem; color: #ccc; }
        .provider-cost {
          font-family: 'JetBrains Mono', monospace;
          font-size: 1.1rem;
          font-weight: 700;
          color: #4dabf7;
          margin-left: auto;
          align-self: flex-end;
          margin-top: -1.4rem;
        }

        /* ── Agent grid ── */
        .agent-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 1.25rem;
        }
        .agent-card {
          background: rgba(24,24,36,0.65);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 14px;
          padding: 1.35rem 1.5rem;
          backdrop-filter: blur(10px);
          transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .agent-card:hover {
          transform: translateY(-2px);
          border-color: rgba(204,93,232,0.3);
        }
        .agent-card-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 0.5rem;
          margin-bottom: 0.5rem;
        }
        .agent-id {
          font-size: 0.88rem;
          color: #ccc;
          font-weight: 600;
          word-break: break-all;
        }
        .agent-cost-badge {
          font-family: 'JetBrains Mono', monospace;
          font-size: 1rem;
          font-weight: 700;
          color: #cc5de8;
          white-space: nowrap;
        }
        .agent-meta {
          display: flex;
          gap: 1rem;
          font-size: 0.72rem;
          color: #555;
          margin-bottom: 0.25rem;
        }

        .empty-msg {
          color: #444;
          font-size: 0.88rem;
          text-align: center;
          padding: 2rem 0;
        }

        .generated-at {
          color: #333;
          font-size: 0.75rem;
          text-align: right;
          margin-top: -0.5rem;
        }
        .link-btn {
          background: none;
          border: none;
          color: #4dabf7;
          cursor: pointer;
          font-size: 0.75rem;
          padding: 0;
          text-decoration: underline;
        }
      `}</style>
    </div>
  );
}
