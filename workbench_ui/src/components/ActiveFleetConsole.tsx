import { useState, useEffect, useCallback } from "react";
import { apiGet, apiPost } from "../app/api-client";

interface MonologueItem {
  timestamp: string;
  system_instruction?: string;
  prompt: string;
  response: string;
}

interface FleetState {
  active_repo: string;
  active_agent: string | null;
  session_id: string;
  status: "idle" | "running" | "done" | "blocked";
  started_at?: string;
  handoff_chain: string[];
  next_agent_id?: string;
  monologue: MonologueItem[];
  errors?: string[];
  output_summary?: string;
  backlog_item_id?: string;
  retry_available?: boolean;
  failure_logged_at?: string;
  blocker_type?: string;
  last_cleared_errors?: string[];
  repo_status?: string;
  status_detail?: string;
  autonomous?: {
    continuous_mode: boolean;
    thread_alive: boolean;
    cycle_running: boolean;
    stopping?: boolean;
    repo_path?: string | null;
    selected_repo: boolean;
    loop_status: "stopped" | "stopping" | "running_selected_repo" | "running_other_repo" | "waiting_between_cycles" | "enabled_for_other_repo";
  };
}

interface ActiveFleetConsoleProps {
  repoPath: string;
  autonomousMode: boolean;
}

const LIVE_TELEMETRY_REFRESH_MS = 2000;

const AGENT_META: Record<string, { name: string; color: string; icon: string; role: string }> = {
  product_poe: { name: "Product Poe", color: "#eab308", icon: "P", role: "Backlog & Product Design" },
  developer_dex: { name: "Developer Dex", color: "#22c55e", icon: "D", role: "Code Implementation" },
  quality_quigon: { name: "Quality Qui-Gon", color: "#3b82f6", icon: "Q", role: "Testing & Validation" },
  thoughtful_thrawn: { name: "Thoughtful Thrawn", color: "#6366f1", icon: "T", role: "Onboarding & Strategy" },
  vibe_vader: { name: "Vibe Vader", color: "#ef4444", icon: "V", role: "HITL & Human Intervention" },
  watcher_wedge: { name: "Watcher Wedge", color: "#f97316", icon: "W", role: "System Health & Failures" },
  optimizer_ahsoka: { name: "Optimizer Ahsoka", color: "#06b6d4", icon: "A", role: "Agent Instruction Tuning" },
  compliance_cody: { name: "Compliance Cody", color: "#6b7280", icon: "C", role: "Regulatory & Compliance Audit" },
};

export default function ActiveFleetConsole({ repoPath, autonomousMode }: ActiveFleetConsoleProps) {
  const [state, setState] = useState<FleetState | null>(null);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retryMessage, setRetryMessage] = useState<string | null>(null);

  const refreshState = useCallback(async () => {
    try {
      const data = await apiGet<FleetState>(`/fleet/active-state?repo_path=${encodeURIComponent(repoPath)}`);
      setState(data);
    } catch (err) {
      console.error("Failed to fetch active state:", err);
    }
  }, [repoPath]);

  const liveTelemetryActive = autonomousMode
    || state?.status === "running"
    || state?.autonomous?.cycle_running === true
    || state?.autonomous?.stopping === true;

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void refreshState();
    }, 0);
    if (!liveTelemetryActive) {
      return () => {
        window.clearTimeout(timeout);
      };
    }

    const interval = window.setInterval(() => {
      void refreshState();
    }, LIVE_TELEMETRY_REFRESH_MS);
    return () => {
      window.clearTimeout(timeout);
      window.clearInterval(interval);
    };
  }, [refreshState, liveTelemetryActive]);

  const clearBlockedState = async () => {
    setRetrying(true);
    setRetryError(null);
    setRetryMessage(null);
    try {
      await apiPost("/fleet/retry-blocked", { repo_path: repoPath });
      await refreshState();
      setRetryMessage("Blocker cleared. The fleet is idle and ready to run again.");
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : "Failed to clear blocked state.");
    } finally {
      setRetrying(false);
    }
  };

  if (!state) return null;

  const currentAgent = state.active_agent ? AGENT_META[state.active_agent] || {
    name: state.active_agent,
    color: "#a855f7",
    icon: "?",
    role: "Specialist Agent"
  } : null;

  const loopStatus = state.autonomous?.loop_status ?? (autonomousMode ? "waiting_between_cycles" : "stopped");
  const displayStatus = state.status === "idle" && loopStatus === "waiting_between_cycles"
    ? "standby"
    : state.status;
  const loopContext = (() => {
    switch (loopStatus) {
      case "running_selected_repo":
        return "Autonomous loop is running a cycle for this repository.";
      case "running_other_repo":
        return "Autonomous loop is running a cycle for another repository.";
      case "stopping":
        return "Autonomous loop is stopping after the current cycle yields.";
      case "waiting_between_cycles":
        return "Autonomous loop is on for this repository and waiting for the next cycle.";
      case "enabled_for_other_repo":
        return "Autonomous loop is on for another repository.";
      default:
        return "Autonomous loop is stopped.";
    }
  })();
  const idleSummary = loopStatus === "waiting_between_cycles"
    ? "No agent is executing right now. The next autonomous cycle will start automatically for the selected repository."
    : "The fleet is idle. Running the autonomous fleet starts work for the selected repository.";

  const getStatusBadgeClass = () => {
    switch (displayStatus) {
      case "running": return "status-running";
      case "blocked": return "status-blocked";
      case "done": return "status-done";
      case "standby": return "status-standby";
      default: return "status-idle";
    }
  };

  const cleanPrompt = (prompt: string) => {
    if (prompt.length > 300) {
      return prompt.substring(0, 300) + "...";
    }
    return prompt;
  };

  const isStaleHeartbeat = state.blocker_type === "stale_heartbeat";

  return (
    <div className="fleet-console glass">
      <div className="console-header">
        <div className="title-area">
          <span className={`console-indicator ${displayStatus}`}></span>
          <h3>Live Fleet Telemetry</h3>
        </div>
        <span className={`status-badge ${getStatusBadgeClass()}`}>
          {displayStatus.toUpperCase()}
        </span>
      </div>
      <div className="loop-context">
        <span>{loopContext}</span>
        {state.status_detail && <span>{state.status_detail}</span>}
      </div>

      {state.status === "idle" && (
        <div className="idle-state">
          <p>{idleSummary}</p>
          {state.last_cleared_errors && state.last_cleared_errors.length > 0 && (
            <p className="last-cleared">Last cleared blocker: {state.last_cleared_errors[0]}</p>
          )}
        </div>
      )}

      {state.status !== "idle" && (
        <div className="active-layout">
          {currentAgent && (
            <div className="agent-status-card" style={{ borderColor: currentAgent.color }}>
              <div className="agent-avatar" style={{ backgroundColor: `${currentAgent.color}22` }}>
                <span className="avatar-icon">{currentAgent.icon}</span>
              </div>
              <div className="agent-info-text">
                <span className="agent-role">{currentAgent.role}</span>
                <h4 style={{ color: currentAgent.color }}>{currentAgent.name}</h4>
                <p className="session-id">Session: <code>{state.session_id || "none"}</code></p>
              </div>
            </div>
          )}

          {state.status === "blocked" && (
            <div className="unblock-guide glass animate-fade-in">
              <div className="guide-header">
                <span className="guide-icon">!</span>
                <h4>{isStaleHeartbeat ? "Stale Session Blocked the Fleet" : "Fleet Blocked"}</h4>
              </div>

              {state.errors && state.errors.length > 0 && (
                <div className="error-traceback">
                  <strong>Traceback Details</strong>
                  <div className="error-scroll">
                    {state.errors.map((err, i) => (
                      <pre key={i} className="error-pre">{err}</pre>
                    ))}
                    {state.output_summary && <pre className="error-pre summary">{state.output_summary}</pre>}
                  </div>
                </div>
              )}

              <div className="blocker-summary">
                {state.backlog_item_id && (
                  <span>Backlog blocker: <code>{state.backlog_item_id}</code></span>
                )}
                {state.failure_logged_at && (
                  <span>Logged: {new Date(state.failure_logged_at).toLocaleString()}</span>
                )}
                {state.blocker_type && (
                  <span>Type: <code>{state.blocker_type}</code></span>
                )}
                <button
                  type="button"
                  className="retry-button"
                  onClick={clearBlockedState}
                  disabled={retrying}
                >
                  {retrying ? "Clearing..." : isStaleHeartbeat ? "Clear Stale Session" : "Clear Blocker for Retry"}
                </button>
                {retryError && <span className="retry-error">{retryError}</span>}
                {retryMessage && <span className="retry-success">{retryMessage}</span>}
              </div>

              <div className="guide-steps">
                <div className="step-card">
                  <div className="step-num">A</div>
                  <div className="step-details">
                    <h5>{isStaleHeartbeat ? "What This Means" : "Fix Runtime Or Logic Errors"}</h5>
                    <p>{isStaleHeartbeat ? "A previous session stopped sending heartbeat updates. Clearing it marks that stale session closed so the supervisor does not keep reporting the old run as active." : "The last agent crashed or hit a validation/policy failure. Inspect the traceback or linked backlog blocker, fix the cause, clear the blocker, then run the fleet again."}</p>
                  </div>
                </div>

                <div className="step-card">
                  <div className="step-num">B</div>
                  <div className="step-details">
                    <h5>Next Action</h5>
                    <p>{isStaleHeartbeat ? "Click Clear Stale Session, then run the autonomous fleet again. If the same session comes back, the supervisor is still seeing an active heartbeat file." : "If this is a human-action item, resolve it in the Action Queue. Otherwise clear the retryable blocker and run the autonomous fleet again."}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="chain-container">
            <h5>Handoff Execution Chain</h5>
            <div className="chain-flow">
              {(state.handoff_chain || []).map((agentId, index) => {
                const meta = AGENT_META[agentId] || { name: agentId, icon: "?" };
                return (
                  <div key={index} className="chain-node">
                    <span className="node-icon">{meta.icon}</span>
                    <span className="node-name">{meta.name}</span>
                    <span className="node-arrow">-&gt;</span>
                  </div>
                );
              })}
              {state.active_agent && (
                <div className="chain-node active" style={{ borderColor: currentAgent?.color }}>
                  <span className="node-icon">{currentAgent?.icon}</span>
                  <span className="node-name" style={{ color: currentAgent?.color }}>{currentAgent?.name}</span>
                  {state.next_agent_id && <span className="node-arrow">-&gt;</span>}
                </div>
              )}
              {state.next_agent_id && (
                <div className="chain-node next">
                  <span className="node-icon">...</span>
                  <span className="node-name">Next: {(AGENT_META[state.next_agent_id] || { name: state.next_agent_id }).name}</span>
                </div>
              )}
            </div>
          </div>

          <div className="thoughts-container">
            <h5>Agent Internal Thoughts</h5>
            {(!state.monologue || state.monologue.length === 0) ? (
              <p className="no-thoughts">No agent thoughts have been recorded for this state.</p>
            ) : (
              <div className="monologue-list">
                {(state.monologue || []).map((item, idx) => {
                  const isExpanded = expandedIndex === idx;
                  return (
                    <div key={idx} className="monologue-item">
                      <div className="monologue-summary" onClick={() => setExpandedIndex(isExpanded ? null : idx)}>
                        <div className="thought-header">
                          <span className="thought-time">{new Date(item.timestamp).toLocaleTimeString()}</span>
                          <span className="thought-action">Thought #{idx + 1} {isExpanded ? "collapse" : "expand"}</span>
                        </div>
                        <p className="thought-snippet">{cleanPrompt(item.prompt)}</p>
                      </div>

                      {isExpanded && (
                        <div className="monologue-detail animate-fade-in">
                          {item.system_instruction && (
                            <div className="thought-block system">
                              <strong>System Directive</strong>
                              <pre>{item.system_instruction}</pre>
                            </div>
                          )}
                          <div className="thought-block prompt">
                            <strong>Self Prompt</strong>
                            <pre>{item.prompt}</pre>
                          </div>
                          <div className="thought-block response">
                            <strong>Reasoned Action / Strategy</strong>
                            <pre>{item.response}</pre>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .fleet-console {
          margin-top: 2rem;
          margin-bottom: 2rem;
          padding: 1.5rem;
          background: rgba(15, 15, 15, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
        }

        .unblock-guide {
          padding: 1.5rem;
          background: rgba(239, 68, 68, 0.05);
          border: 1px solid rgba(239, 68, 68, 0.2);
          border-radius: 8px;
          margin-bottom: 0.5rem;
        }

        .guide-header {
          display: flex;
          align-items: center;
          gap: 0.6rem;
          margin-bottom: 1rem;
        }

        .guide-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 22px;
          height: 22px;
          border-radius: 50%;
          background: rgba(239, 68, 68, 0.2);
          color: #fca5a5;
          font-weight: 800;
        }

        .guide-header h4 {
          margin: 0;
          font-size: 1.1rem;
          font-weight: 700;
          color: #fca5a5;
        }

        .error-traceback {
          margin-bottom: 1.2rem;
          padding: 1rem;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(239, 68, 68, 0.15);
          border-radius: 8px;
        }

        .error-traceback strong {
          display: block;
          font-size: 0.8rem;
          text-transform: uppercase;
          color: #fca5a5;
          letter-spacing: 0.5px;
          margin-bottom: 0.5rem;
        }

        .error-scroll {
          max-height: 200px;
          overflow-y: auto;
        }

        .error-pre {
          margin: 0;
          font-family: 'Courier New', Courier, monospace;
          font-size: 0.8rem;
          color: #ef4444;
          white-space: pre-wrap;
          word-break: break-word;
        }

        .error-pre.summary {
          margin-top: 0.5rem;
          color: #fca5a5;
          border-top: 1px dashed rgba(239, 68, 68, 0.2);
          padding-top: 0.5rem;
        }

        .guide-steps {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1.2rem;
        }

        .blocker-summary {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.75rem;
          margin-bottom: 1.2rem;
          padding: 0.8rem;
          background: rgba(0, 0, 0, 0.25);
          border: 1px solid rgba(239, 68, 68, 0.15);
          border-radius: 8px;
          color: #d1d5db;
          font-size: 0.82rem;
        }

        .blocker-summary code {
          background: rgba(255, 255, 255, 0.08);
          padding: 2px 5px;
          border-radius: 4px;
          color: #fca5a5;
        }

        .retry-button {
          margin-left: auto;
          padding: 0.45rem 0.7rem;
          border: 1px solid rgba(248, 113, 113, 0.45);
          border-radius: 8px;
          background: rgba(127, 29, 29, 0.35);
          color: #fee2e2;
          font-weight: 700;
          cursor: pointer;
        }

        .retry-button:disabled {
          opacity: 0.65;
          cursor: wait;
        }

        .retry-error {
          width: 100%;
          color: #fca5a5;
        }

        .retry-success {
          width: 100%;
          color: #86efac;
        }

        .step-card {
          display: flex;
          gap: 1rem;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.04);
          padding: 1rem;
          border-radius: 8px;
        }

        .step-num {
          display: flex;
          align-items: center;
          justify-content: center;
          min-width: 28px;
          height: 28px;
          border-radius: 50%;
          background: rgba(239, 68, 68, 0.2);
          border: 1px solid rgba(239, 68, 68, 0.4);
          color: #fca5a5;
          font-weight: 700;
          font-size: 0.85rem;
        }

        .step-details h5 {
          margin: 0 0 0.3rem 0;
          font-size: 0.9rem;
          color: #e5e7eb;
          font-weight: 600;
        }

        .step-details p {
          margin: 0;
          font-size: 0.8rem;
          color: #9ca3af;
          line-height: 1.4;
        }

        .console-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 1rem;
          margin-bottom: 1.2rem;
        }

        .title-area {
          display: flex;
          align-items: center;
          gap: 0.8rem;
        }

        .console-indicator {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: #6b7280;
          box-shadow: 0 0 10px #6b7280;
        }

        .console-indicator.running {
          background: #22c55e;
          box-shadow: 0 0 10px #22c55e;
        }

        .console-indicator.standby {
          background: #f59e0b;
          box-shadow: 0 0 10px #f59e0b;
        }

        .console-indicator.blocked {
          background: #ef4444;
          box-shadow: 0 0 10px #ef4444;
        }

        .console-indicator.done {
          background: #3b82f6;
          box-shadow: 0 0 10px #3b82f6;
        }

        .status-badge {
          padding: 0.3rem 0.8rem;
          border-radius: 20px;
          font-size: 0.8rem;
          font-weight: 700;
          letter-spacing: 0.5px;
        }

        .status-running {
          background: rgba(34, 197, 94, 0.2);
          border: 1px solid #22c55e;
          color: #4ade80;
        }

        .status-blocked {
          background: rgba(239, 68, 68, 0.2);
          border: 1px solid #ef4444;
          color: #fca5a5;
        }

        .status-done {
          background: rgba(59, 130, 246, 0.2);
          border: 1px solid #3b82f6;
          color: #93c5fd;
        }

        .status-standby {
          background: rgba(245, 158, 11, 0.16);
          border: 1px solid #f59e0b;
          color: #fcd34d;
        }

        .status-idle {
          background: rgba(107, 114, 128, 0.2);
          border: 1px solid #6b7280;
          color: #d1d5db;
        }

        .loop-context {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          margin: -0.35rem 0 1.2rem;
          color: #cbd5e1;
          font-size: 0.9rem;
          line-height: 1.4;
        }

        .idle-state {
          text-align: center;
          padding: 2rem 0;
          color: #9ca3af;
        }

        .last-cleared {
          margin-top: 0.75rem;
          color: #d1d5db;
          font-size: 0.85rem;
        }

        .active-layout {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }

        .agent-status-card {
          display: flex;
          align-items: center;
          gap: 1.2rem;
          padding: 1.2rem;
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid;
          border-radius: 8px;
        }

        .agent-avatar {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 50px;
          height: 50px;
          border-radius: 8px;
        }

        .avatar-icon {
          font-size: 1.2rem;
          font-weight: 800;
        }

        .agent-info-text h4 {
          margin: 0.1rem 0;
          font-size: 1.2rem;
          font-weight: 700;
        }

        .agent-role {
          font-size: 0.75rem;
          color: #9ca3af;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .session-id {
          font-size: 0.75rem;
          color: #9ca3af;
        }

        .session-id code {
          background: rgba(255, 255, 255, 0.06);
          padding: 1px 4px;
          border-radius: 4px;
        }

        .chain-container h5, .thoughts-container h5 {
          font-size: 0.9rem;
          color: #d1d5db;
          margin-bottom: 0.8rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .chain-flow {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.5rem;
          padding: 1rem;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
        }

        .chain-node {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          padding: 0.4rem 0.8rem;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          font-size: 0.85rem;
        }

        .chain-node.active {
          border: 1px solid;
          background: rgba(255, 255, 255, 0.06);
          font-weight: 700;
        }

        .chain-node.next {
          border: 1px dashed rgba(255, 255, 255, 0.2);
          color: #9ca3af;
        }

        .node-arrow {
          color: #6b7280;
          margin-left: 0.5rem;
        }

        .thoughts-container {
          background: rgba(0, 0, 0, 0.2);
          padding: 1.2rem;
          border-radius: 8px;
        }

        .no-thoughts {
          color: #9ca3af;
          font-style: italic;
          font-size: 0.9rem;
        }

        .monologue-list {
          display: flex;
          flex-direction: column;
          gap: 0.8rem;
        }

        .monologue-item {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          overflow: hidden;
        }

        .monologue-summary {
          padding: 0.8rem;
          cursor: pointer;
          transition: background 0.2s ease;
        }

        .monologue-summary:hover {
          background: rgba(255, 255, 255, 0.04);
        }

        .thought-header {
          display: flex;
          justify-content: space-between;
          font-size: 0.75rem;
          color: #9ca3af;
          margin-bottom: 0.4rem;
        }

        .thought-snippet {
          margin: 0;
          font-size: 0.85rem;
          color: #e5e7eb;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .monologue-detail {
          padding: 1rem;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          background: rgba(0, 0, 0, 0.3);
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .thought-block {
          display: flex;
          flex-direction: column;
          gap: 0.4rem;
        }

        .thought-block strong {
          font-size: 0.8rem;
          text-transform: uppercase;
          color: #9ca3af;
          letter-spacing: 0.5px;
        }

        .thought-block pre {
          margin: 0;
          padding: 0.8rem;
          background: rgba(0, 0, 0, 0.5);
          border-radius: 6px;
          font-family: 'Courier New', Courier, monospace;
          font-size: 0.8rem;
          color: #38bdf8;
          white-space: pre-wrap;
          word-break: break-word;
          max-height: 250px;
          overflow-y: auto;
        }

        .thought-block.response pre {
          color: #34d399;
        }

        .thought-block.system pre {
          color: #fb923c;
        }

        .animate-fade-in {
          animation: fadeIn 0.3s ease-out;
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-5px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 768px) {
          .guide-steps {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
