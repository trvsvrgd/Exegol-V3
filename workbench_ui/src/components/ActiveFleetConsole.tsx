import { useState, useEffect } from "react";
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
}

interface ActiveFleetConsoleProps {
  repoPath: string;
  autonomousMode: boolean;
}

const AGENT_META: Record<string, { name: string; color: string; icon: string; role: string }> = {
  product_poe: { name: "Product Poe", color: "#eab308", icon: "⚪", role: "Backlog & Product Design" },
  developer_dex: { name: "Developer Dex", color: "#22c55e", icon: "👨‍🔧", role: "Code Implementation" },
  quality_quigon: { name: "Quality Qui-Gon", color: "#3b82f6", icon: "⚔️", role: "Testing & Validation" },
  thoughtful_thrawn: { name: "Thoughtful Thrawn", color: "#6366f1", icon: "🧠", role: "Onboarding & Strategy" },
  vibe_vader: { name: "Vibe Vader", color: "#ef4444", icon: "🔴", role: "HITL & Human Intervention" },
  watcher_wedge: { name: "Watcher Wedge", color: "#f97316", icon: "📡", role: "System Health & Failures" },
  optimizer_ahsoka: { name: "Optimizer Ahsoka", color: "#06b6d4", icon: "💪", role: "Agent Instruction Tuning" },
  compliance_cody: { name: "Compliance Cody", color: "#6b7280", icon: "📋", role: "Regulatory & Compliance Audit" },
};

export default function ActiveFleetConsole({ repoPath, autonomousMode }: ActiveFleetConsoleProps) {
  const [state, setState] = useState<FleetState | null>(null);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchState() {
      try {
        const data = await apiGet<FleetState>(`/fleet/active-state?repo_path=${encodeURIComponent(repoPath)}`);
        setState(data);
      } catch (err) {
        console.error("Failed to fetch active fleet state:", err);
      }
    }

    fetchState();
    // Poll more frequently if fleet is running
    const interval = setInterval(fetchState, 2000);

    return () => clearInterval(interval);
  }, [repoPath]);

  const refreshState = async () => {
    const data = await apiGet<FleetState>(`/fleet/active-state?repo_path=${encodeURIComponent(repoPath)}`);
    setState(data);
  };

  const clearBlockedState = async () => {
    setRetrying(true);
    setRetryError(null);
    try {
      await apiPost("/fleet/retry-blocked", { repo_path: repoPath });
      await refreshState();
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
    icon: "🤖",
    role: "Specialist Agent"
  } : null;

  const getStatusBadgeClass = () => {
    switch (state.status) {
      case "running": return "status-running";
      case "blocked": return "status-blocked";
      case "done": return "status-done";
      default: return "status-idle";
    }
  };

  const cleanPrompt = (prompt: string) => {
    if (prompt.length > 300) {
      return prompt.substring(0, 300) + "...";
    }
    return prompt;
  };

  return (
    <div className="fleet-console glass">
      <div className="console-header">
        <div className="title-area">
          <span className="console-indicator animate-pulse"></span>
          <h3>Live Fleet Telemetry</h3>
        </div>
        <span className={`status-badge ${getStatusBadgeClass()}`}>
          {state.status.toUpperCase()}
        </span>
      </div>

      {state.status === "idle" && (
        <div className="idle-state">
          <p>
            💤 The Fleet is currently resting. Waking Poe or triggering &quot;Go&quot; starts autonomous operations.
            {autonomousMode && " Autonomous mode is enabled and waiting for the next cycle."}
          </p>
        </div>
      )}

      {state.status !== "idle" && (
        <div className="active-layout">
          {/* Active Agent card */}
          {currentAgent && (
            <div className="agent-status-card" style={{ borderColor: currentAgent.color }}>
              <div className="agent-avatar" style={{ backgroundColor: `${currentAgent.color}22` }}>
                <span className="avatar-icon">{currentAgent.icon}</span>
              </div>
              <div className="agent-info-text">
                <span className="agent-role">{currentAgent.role}</span>
                <h4 style={{ color: currentAgent.color }}>{currentAgent.name}</h4>
                <p className="session-id">Session: <code>{state.session_id}</code></p>
              </div>
            </div>
          )}

          {/* Troubleshooting / Unblocking Guide */}
          {state.status === "blocked" && (
            <div className="unblock-guide glass animate-fade-in">
              <div className="guide-header">
                <span className="guide-icon">🛡️</span>
                <h4>How to Unblock the Fleet</h4>
              </div>
              
              {state.errors && state.errors.length > 0 && (
                <div className="error-traceback">
                  <strong>Traceback Details:</strong>
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
                <button
                  type="button"
                  className="retry-button"
                  onClick={clearBlockedState}
                  disabled={retrying}
                >
                  {retrying ? "Clearing..." : "Clear Blocker for Retry"}
                </button>
                {retryError && <span className="retry-error">{retryError}</span>}
              </div>
              
              <div className="guide-steps">
                <div className="step-card">
                  <div className="step-num">A</div>
                  <div className="step-details">
                    <h5>Fix Underlying Runtime & Logic Errors</h5>
                    <p>The last agent crashed or hit a validation/policy failure during execution. Inspect the Traceback Details or the linked backlog blocker, apply the fix, clear the blocker here, then click <strong>&quot;Go&quot;</strong> or <strong>&quot;Start Autonomous Fleet&quot;</strong> to retry.</p>
                  </div>
                </div>
                
                <div className="step-card">
                  <div className="step-num">B</div>
                  <div className="step-details">
                    <h5>Resolve Human Interventions (HITL Queue)</h5>
                    <p>The fleet might be paused waiting for critical credentials, token key rotations, or manual decisions. Scroll down to the <strong>Vibe Vader (Action Queue & Interventions)</strong> section below, complete the required task, and click <strong>&quot;Mark as Resolved&quot;</strong> or <strong>&quot;Dismiss&quot;</strong> to clear the blocker.</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Handoff chain */}
          <div className="chain-container">
            <h5>Handoff Execution Chain</h5>
            <div className="chain-flow">
              {state.handoff_chain.map((agentId, index) => {
                const meta = AGENT_META[agentId] || { name: agentId, icon: "🤖" };
                return (
                  <div key={index} className="chain-node">
                    <span className="node-icon">{meta.icon}</span>
                    <span className="node-name">{meta.name}</span>
                    <span className="node-arrow">→</span>
                  </div>
                );
              })}
              {state.active_agent && (
                <div className="chain-node active" style={{ borderColor: currentAgent?.color }}>
                  <span className="node-icon">{currentAgent?.icon}</span>
                  <span className="node-name" style={{ color: currentAgent?.color }}>{currentAgent?.name}</span>
                  {state.next_agent_id && <span className="node-arrow">→</span>}
                </div>
              )}
              {state.next_agent_id && (
                <div className="chain-node next">
                  <span className="node-icon">⏳</span>
                  <span className="node-name">Next: {(AGENT_META[state.next_agent_id] || { name: state.next_agent_id }).name}</span>
                </div>
              )}
            </div>
          </div>

          {/* Thoughts monologue */}
          <div className="thoughts-container">
            <h5>Agent Internal Thoughts (Monologue)</h5>
            {state.monologue.length === 0 ? (
              <p className="no-thoughts">Analyzing context, awaiting first generation...</p>
            ) : (
              <div className="monologue-list">
                {state.monologue.map((item, idx) => {
                  const isExpanded = expandedIndex === idx;
                  return (
                    <div key={idx} className="monologue-item">
                      <div className="monologue-summary" onClick={() => setExpandedIndex(isExpanded ? null : idx)}>
                        <div className="thought-header">
                          <span className="thought-time">{new Date(item.timestamp).toLocaleTimeString()}</span>
                          <span className="thought-action">Thought #{idx + 1} {isExpanded ? "▲" : "▼"}</span>
                        </div>
                        <p className="thought-snippet">{cleanPrompt(item.prompt)}</p>
                      </div>
                      
                      {isExpanded && (
                        <div className="monologue-detail animate-fade-in">
                          {item.system_instruction && (
                            <div className="thought-block system">
                              <strong>System Directive:</strong>
                              <pre>{item.system_instruction}</pre>
                            </div>
                          )}
                          <div className="thought-block prompt">
                            <strong>Self Prompt:</strong>
                            <pre>{item.prompt}</pre>
                          </div>
                          <div className="thought-block response">
                            <strong>Reasoned Action / Strategy:</strong>
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
          border-radius: 16px;
        }

        .unblock-guide {
          padding: 1.5rem;
          background: rgba(239, 68, 68, 0.05);
          border: 1px solid rgba(239, 68, 68, 0.2);
          border-radius: 12px;
          margin-bottom: 0.5rem;
        }

        .guide-header {
          display: flex;
          align-items: center;
          gap: 0.6rem;
          margin-bottom: 1rem;
        }

        .guide-icon {
          font-size: 1.4rem;
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
          word-break: break-all;
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

        @media (max-width: 768px) {
          .guide-steps {
            grid-template-columns: 1fr;
          }
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
          background: #22c55e;
          box-shadow: 0 0 10px #22c55e;
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

        .status-idle {
          background: rgba(107, 114, 128, 0.2);
          border: 1px solid #6b7280;
          color: #d1d5db;
        }

        .idle-state {
          text-align: center;
          padding: 2rem 0;
          color: #9ca3af;
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
          border-radius: 12px;
        }

        .agent-avatar {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 50px;
          height: 50px;
          border-radius: 12px;
        }

        .avatar-icon {
          font-size: 1.8rem;
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
          border-radius: 10px;
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
          border-radius: 12px;
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
          word-break: break-all;
          max-height: 250px;
          overflow-y: auto;
        }

        .thought-block.response pre {
          color: #34d399;
        }

        .thought-block.system pre {
          color: #fb923c;
        }

        .animate-pulse {
          animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: .4; }
        }

        .animate-fade-in {
          animation: fadeIn 0.3s ease-out;
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-5px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
