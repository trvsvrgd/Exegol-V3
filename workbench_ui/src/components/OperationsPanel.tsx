"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../app/api-client";

interface OperationsPanelProps {
  repoPath: string;
}

interface LatestBlocker {
  id: string;
  task: string;
  blocker_type?: string;
  context?: string;
  status?: string;
}

interface OperationsState {
  status: string;
  backend: { status: string; pid?: number };
  components: Record<string, { status: string; detail?: string; blocker_type?: string }>;
  scheduler: { status: string; enabled: boolean; heartbeat?: string | null };
  autonomous_loop: { status: string };
  active_agent?: string | null;
  queue_length: number;
  latest_blocker?: LatestBlocker | null;
  latest_blocker_type?: string | null;
  recent_failures: Array<{ timestamp?: string; agent_id?: string; outcome?: string; errors?: string[] }>;
  health_report: unknown;
}

export default function OperationsPanel({ repoPath }: OperationsPanelProps) {
  const [ops, setOps] = useState<OperationsState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const data = await apiGet<OperationsState>(`/fleet/operations?repo_path=${encodeURIComponent(repoPath)}`);
      setOps(data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("Unable to load operations state.");
    }
  };

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 10000);
    return () => window.clearInterval(id);
  }, [repoPath]);

  const act = async (action: "clear" | "retry" | "autonomous") => {
    if (!ops) return;
    setBusy(action);
    try {
      if (action === "clear" && ops.latest_blocker) {
        await apiPost("/blockers/clear", { repo_path: repoPath, blocker_id: ops.latest_blocker.id });
      }
      if (action === "retry" && ops.latest_blocker) {
        await apiPost("/blockers/retry-go", { repo_path: repoPath, blocker_id: ops.latest_blocker.id });
      }
      if (action === "autonomous") {
        await apiPost("/autonomous/start", { repo_path: repoPath });
      }
      await refresh();
    } catch (err) {
      console.error(err);
      setError("Operation failed. Check blocker state and backend logs.");
    } finally {
      setBusy(null);
    }
  };

  if (error) return <div className="ops-error">{error}</div>;
  if (!ops) return <div className="ops-loading">Loading operations...</div>;

  const componentEntries = Object.entries({
    backend: ops.backend,
    docker: ops.components.docker,
    scheduler: ops.scheduler,
    autonomous_loop: ops.autonomous_loop,
    frontend: ops.components.frontend,
  }).filter(([, value]) => Boolean(value));

  return (
    <section className="ops-panel">
      <div className="ops-header">
        <div>
          <h2>Operations</h2>
          <span className={`status ${ops.status}`}>{ops.status}</span>
        </div>
        <button className="export-btn" onClick={() => navigator.clipboard.writeText(JSON.stringify(ops.health_report, null, 2))}>
          Export Health
        </button>
      </div>

      <div className="ops-grid">
        {componentEntries.map(([name, value]) => (
          <div key={name} className="ops-tile">
            <span className="tile-label">{name.replace("_", " ")}</span>
            <strong>{value.status}</strong>
            {"pid" in value && value.pid ? <small>PID {value.pid}</small> : null}
            {"blocker_type" in value && value.blocker_type ? <small>{value.blocker_type}</small> : null}
          </div>
        ))}
        <div className="ops-tile">
          <span className="tile-label">Active Agent</span>
          <strong>{ops.active_agent || "idle"}</strong>
        </div>
        <div className="ops-tile">
          <span className="tile-label">Queue</span>
          <strong>{ops.queue_length}</strong>
        </div>
      </div>

      <div className="blocker-row">
        <div>
          <span className="tile-label">Latest Blocker</span>
          <strong>{ops.latest_blocker?.task || "None"}</strong>
          {ops.latest_blocker_type ? <small>{ops.latest_blocker_type}</small> : null}
        </div>
        <div className="ops-actions">
          <button disabled={!ops.latest_blocker || busy !== null} onClick={() => void act("clear")}>Clear</button>
          <button disabled={!ops.latest_blocker || busy !== null} onClick={() => void act("retry")}>Retry Go</button>
          <button disabled={busy !== null} onClick={() => void act("autonomous")}>Start Autonomous</button>
        </div>
      </div>

      <div className="failure-timeline">
        <h3>Recent Failures</h3>
        {ops.recent_failures.length === 0 ? (
          <p>No recent failures.</p>
        ) : (
          ops.recent_failures.map((failure, index) => (
            <div key={`${failure.timestamp}-${index}`} className="failure-item">
              <span>{failure.timestamp || "unknown time"}</span>
              <strong>{failure.agent_id || "unknown"} - {failure.outcome}</strong>
              <small>{failure.errors?.join("; ") || "No error detail"}</small>
            </div>
          ))
        )}
      </div>

      <style jsx>{`
        .ops-panel { display: flex; flex-direction: column; gap: 1rem; }
        .ops-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
        .ops-header h2 { margin: 0 0 0.4rem; font-size: 1.4rem; }
        .status { text-transform: uppercase; font-size: 0.8rem; font-weight: 700; }
        .status.healthy { color: #4ade80; }
        .status.degraded { color: #fbbf24; }
        .ops-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.8rem; }
        .ops-tile, .blocker-row, .failure-timeline { border: 1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,0.25); border-radius: 8px; padding: 1rem; }
        .ops-tile { min-height: 96px; display: flex; flex-direction: column; gap: 0.35rem; }
        .tile-label { color: var(--text-secondary); font-size: 0.76rem; text-transform: uppercase; }
        strong { color: white; overflow-wrap: anywhere; }
        small { color: var(--text-secondary); overflow-wrap: anywhere; }
        .blocker-row { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
        .ops-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        button { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.16); color: white; border-radius: 8px; padding: 0.65rem 0.9rem; cursor: pointer; }
        button:disabled { opacity: 0.5; cursor: not-allowed; }
        .export-btn { white-space: nowrap; }
        .failure-timeline { display: flex; flex-direction: column; gap: 0.75rem; }
        .failure-timeline h3 { margin: 0; font-size: 1rem; }
        .failure-item { border-top: 1px solid rgba(255,255,255,0.08); padding-top: 0.7rem; display: flex; flex-direction: column; gap: 0.25rem; }
        .failure-item span, .ops-loading, .ops-error { color: var(--text-secondary); }
        @media (max-width: 700px) { .blocker-row, .ops-header { align-items: flex-start; flex-direction: column; } }
      `}</style>
    </section>
  );
}
