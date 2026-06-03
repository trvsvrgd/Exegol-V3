"use client";

import { useState, useEffect, useCallback } from "react";
import ActionQueue from "../components/ActionQueue";
import BacklogBoard from "../components/BacklogBoard";
import QuickAddTask from "../components/QuickAddTask";
import ThrawnInteraction from "../components/ThrawnInteraction";
import ActiveFleetConsole from "../components/ActiveFleetConsole";
import PoeRoadmapBrief from "../components/PoeRoadmapBrief";

import { apiGet, apiPost, getLocalActiveRepo, setLocalActiveRepo } from "../app/api-client";

interface Repo {
  repo_path: string;
  model_routing_preference: string;
  priority: number;
  agent_status: string;
  status_detail?: string;
  blocker_type?: string;
}

interface AutonomousStatus {
  continuous_mode: boolean;
  thread_alive: boolean;
  cycle_running: boolean;
  stopping?: boolean;
  repo_path?: string | null;
}

interface SupervisorHealth {
  status: "ok" | "degraded";
  checked_at: string;
  degraded_services: string[];
  degraded_repositories: string[];
}

const ACTIVE_STATUS_REFRESH_MS = 5000;
const STOPPED_STATUS_REFRESH_MS = 30000;
const ACTIVE_SUPERVISOR_REFRESH_MS = 15000;
const ACTIVE_REPO_REFRESH_MS = 5000;
const STOPPED_REPO_REFRESH_MS = 30000;
const BACKEND_OFFLINE_MESSAGE = "Exegol backend is unreachable. Start the backend and leave it running before using fleet controls.";

function isBackendNetworkError(error: unknown): boolean {
  const name = error instanceof Error ? error.name : "";
  const message = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase();
  return name === "AbortError" || message.includes("failed to fetch") || message.includes("networkerror") || message.includes("aborted");
}

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string | null>(() => getLocalActiveRepo() || null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<'poe' | 'thrawn' | 'vader'>('poe');
  const [autonomousMode, setAutonomousMode] = useState<boolean>(false);
  const [cycleRunning, setCycleRunning] = useState<boolean>(false);
  const [stopping, setStopping] = useState<boolean>(false);
  const [controlBusy, setControlBusy] = useState<boolean>(false);
  const [controlError, setControlError] = useState<string | null>(null);
  const [controlMessage, setControlMessage] = useState<string | null>(null);
  const [supervisorHealth, setSupervisorHealth] = useState<SupervisorHealth | null>(null);
  const [backendReachable, setBackendReachable] = useState<boolean>(true);
  const [repoPathInput, setRepoPathInput] = useState<string>("");
  const [repoRegistering, setRepoRegistering] = useState<boolean>(false);
  const [repoRegisterMessage, setRepoRegisterMessage] = useState<string | null>(null);
  const fleetActive = autonomousMode || cycleRunning || stopping;
  const statusRefreshActive = fleetActive || !backendReachable;

  const fetchAutonomousStatus = useCallback(async () => {
    try {
      const data = await apiGet<AutonomousStatus>("/fleet/autonomous-status");
      setBackendReachable(true);
      setFetchError(null);
      setAutonomousMode(data.continuous_mode);
      setCycleRunning(data.cycle_running);
      setStopping(Boolean(data.stopping));
    } catch (e) {
      console.error("Failed to fetch autonomous status", e);
      setBackendReachable(false);
      setAutonomousMode(false);
      setCycleRunning(false);
      setStopping(false);
      setFetchError(BACKEND_OFFLINE_MESSAGE);
    }
  }, []);

  const fetchSupervisorHealth = useCallback(async () => {
    try {
      const data = await apiGet<SupervisorHealth>("/fleet/supervisor-health");
      setSupervisorHealth(data);
    } catch (e) {
      console.error("Failed to fetch supervisor health", e);
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchAutonomousStatus();
    }, 0);
    const interval = window.setInterval(
      () => void fetchAutonomousStatus(),
      statusRefreshActive ? ACTIVE_STATUS_REFRESH_MS : STOPPED_STATUS_REFRESH_MS
    );
    return () => {
      window.clearTimeout(timeout);
      window.clearInterval(interval);
    };
  }, [fetchAutonomousStatus, statusRefreshActive]);

  useEffect(() => {
    if (!controlMessage) return;
    const timeout = window.setTimeout(() => setControlMessage(null), 6000);
    return () => window.clearTimeout(timeout);
  }, [controlMessage]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchSupervisorHealth();
    }, 0);
    if (!fleetActive) {
      return () => {
        window.clearTimeout(timeout);
      };
    }

    const interval = window.setInterval(() => void fetchSupervisorHealth(), ACTIVE_SUPERVISOR_REFRESH_MS);
    return () => {
      window.clearTimeout(timeout);
      window.clearInterval(interval);
    };
  }, [fetchSupervisorHealth, fleetActive]);

  const setAutonomousFleet = async (enabled: boolean) => {
    setControlBusy(true);
    setControlError(null);
    setControlMessage(null);
    try {
      const endpoint = enabled ? "/fleet/start-autonomous" : "/fleet/stop-autonomous";
      const payload = enabled && activeRepo ? { repo_path: activeRepo } : {};
      const data = await apiPost<AutonomousStatus & {status: string}>(endpoint, payload);
      setAutonomousMode(data.continuous_mode);
      setCycleRunning(data.cycle_running);
      setStopping(Boolean(data.stopping));
      setBackendReachable(true);
      setFetchError(null);
      setControlMessage(
        enabled
          ? "Autonomous fleet loop started."
          : data.stopping
            ? "Stop requested. The fleet will pause after the current cycle yields."
            : "Autonomous fleet loop stopped."
      );
    } catch (e) {
      console.error("Failed to toggle autonomous mode", e);
      if (isBackendNetworkError(e)) {
        setBackendReachable(false);
        setStopping(false);
        setFetchError(BACKEND_OFFLINE_MESSAGE);
        setControlError(BACKEND_OFFLINE_MESSAGE);
      } else {
        setControlError("Fleet control request failed. Check backend logs.");
      }
    } finally {
      setControlBusy(false);
    }
  };

  const runAutonomousFleet = async () => {
    if (!activeRepo) return;
    setControlBusy(true);
    setControlError(null);
    setControlMessage(null);
    try {
      const data = await apiPost<AutonomousStatus & {status: string}>("/fleet/start-autonomous", { repo_path: activeRepo });
      setAutonomousMode(data.continuous_mode);
      setCycleRunning(data.cycle_running);
      setStopping(Boolean(data.stopping));
      setBackendReachable(true);
      setFetchError(null);
      setControlMessage("Autonomous fleet loop started for the selected repository.");
    } catch (e) {
      console.error("Failed to run autonomous fleet", e);
      if (isBackendNetworkError(e)) {
        setBackendReachable(false);
        setFetchError(BACKEND_OFFLINE_MESSAGE);
        setControlError(BACKEND_OFFLINE_MESSAGE);
      } else {
        setControlError("Fleet run request failed. Check backend logs.");
      }
    } finally {
      setControlBusy(false);
    }
  };

  const fetchRepos = useCallback(async () => {
    try {
      const data = await apiGet<Repo[]>("/repos");
      setBackendReachable(true);
      setFetchError(null);
      setRepos(data);
      if (data.length > 0) {
        const savedRepo = getLocalActiveRepo();
        if (savedRepo && data.some((r) => r.repo_path === savedRepo)) {
          if (activeRepo !== savedRepo) {
            setActiveRepo(savedRepo);
          }
        } else if (!activeRepo) {
          setActiveRepo(data[0].repo_path);
          setLocalActiveRepo(data[0].repo_path);
        }
      }
    } catch (err) {
      console.error("Failed to fetch repos:", err);
      if (isBackendNetworkError(err)) {
        setBackendReachable(false);
        setFetchError(BACKEND_OFFLINE_MESSAGE);
      } else {
        setFetchError("Unable to load repository list. Check backend connectivity.");
      }
    }
  }, [activeRepo]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchRepos();
    }, 0);
    const refreshMs = fleetActive ? ACTIVE_REPO_REFRESH_MS : STOPPED_REPO_REFRESH_MS;
    const interval = window.setInterval(() => {
      void fetchRepos();
    }, refreshMs);
    return () => {
      window.clearTimeout(timeout);
      window.clearInterval(interval);
    };
  }, [fetchRepos, fleetActive]);

  const registerRepository = async () => {
    const repoPath = repoPathInput.trim();
    if (!repoPath) return;
    setRepoRegistering(true);
    setRepoRegisterMessage(null);
    try {
      const result = await apiPost<{ status: string; repo: Repo }>("/repos/register", { repo_path: repoPath });
      setActiveRepo(result.repo.repo_path);
      setLocalActiveRepo(result.repo.repo_path);
      setRepoPathInput("");
      setRepoRegisterMessage(result.status === "added" ? "Repository registered." : "Repository already registered.");
      await fetchRepos();
    } catch (err) {
      console.error("Failed to register repository:", err);
      setRepoRegisterMessage("Repository registration failed. Confirm the path exists and contains .git.");
    } finally {
      setRepoRegistering(false);
    }
  };

  const activeRepoMeta = repos.find((repo) => repo.repo_path === activeRepo);
  const stopControlActive = autonomousMode || stopping || cycleRunning;
  const fleetControlLabel = !backendReachable
    ? "Backend Offline"
    : stopping
      ? "Force Stop Fleet"
      : stopControlActive
      ? "Stop Autonomous Fleet"
      : "Run Autonomous Fleet";
  const attentionItems = supervisorHealth?.status === "degraded"
    ? [
        ...supervisorHealth.degraded_services,
        ...supervisorHealth.degraded_repositories.map((repo) => repo.split(/[/\\]/).filter(Boolean).slice(-1)[0]),
      ]
    : [];
  const activeBlockerDetail = activeRepoMeta?.agent_status === "blocked" ? activeRepoMeta.status_detail : null;

  return (
    <div className="container dashboard-container">
      <header className="page-header">
        <h1 className="title-glow">Exegol Command Center</h1>
        <p className="subtitle">Select your target repository and engage with the agent fleet.</p>
        <div className="fleet-controls" style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'center', gap: '1rem' }}>
          <button
            className="fleet-toggle-btn"
            onClick={stopControlActive ? () => setAutonomousFleet(false) : runAutonomousFleet}
            disabled={!backendReachable || controlBusy || (!stopControlActive && !activeRepo)}
            title={!backendReachable ? "The Exegol backend is not reachable." : stopControlActive ? "Stop autonomous fleet work and release local model resources." : "Run the autonomous fleet for the selected repository."}
          >
            {fleetControlLabel}
          </button>
        </div>
        {controlError && <div className="error-banner control-error">{controlError}</div>}
        {controlMessage && supervisorHealth?.status !== "degraded" && <div className="success-banner control-error">{controlMessage}</div>}
        {supervisorHealth?.status === "degraded" && (
          <div className="error-banner control-error">
            Needs attention:
            {" "}
            {attentionItems.join(", ")}
            {activeBlockerDetail ? ` - ${activeBlockerDetail}` : ""}
          </div>
        )}
      </header>

      {fetchError && <div className="error-banner">{fetchError}</div>}

      <section className="repo-selection-panel glass">
        <div className="repo-info">
          <h2>Active Repository</h2>
          <div className="repo-selector">
            {repos.map((repo) => {
              const pathParts = repo.repo_path.split(/[/\\]/).filter(Boolean);
              const label = pathParts.slice(-1)[0];
              return (
                <button
                  key={repo.repo_path}
                  className={`repo-pill ${repo.repo_path === activeRepo ? "active" : ""}`}
                  onClick={() => {
                    setActiveRepo(repo.repo_path);
                    setLocalActiveRepo(repo.repo_path);
                  }}
                  title={repo.repo_path}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <div className="repo-register">
            <input
              type="text"
              value={repoPathInput}
              onChange={(event) => setRepoPathInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void registerRepository();
                }
              }}
              placeholder="Paste cloned GitHub repo path"
              aria-label="Repository path"
            />
            <button
              type="button"
              onClick={registerRepository}
              disabled={repoRegistering || !repoPathInput.trim()}
            >
              {repoRegistering ? "Registering" : "Register Repo"}
            </button>
          </div>
          {repoRegisterMessage && <div className="repo-register-message">{repoRegisterMessage}</div>}
        </div>

        {activeRepoMeta ? (
          <div className="repo-stats">
            <div className="stat-card">
              <span className="stat-label">Model Routing</span>
              <strong className="stat-value">{activeRepoMeta.model_routing_preference}</strong>
            </div>
            <div className="stat-card">
              <span className="stat-label">Priority Level</span>
              <strong className="stat-value">{activeRepoMeta.priority}</strong>
            </div>
            <div className="stat-card">
              <span className="stat-label">Agent Status</span>
              <strong className={`stat-value ${activeRepoMeta.agent_status === "blocked" ? "status-blocked-text" : "status-active"}`}>{activeRepoMeta.agent_status || "Online"}</strong>
              {activeRepoMeta.status_detail && <span className="stat-detail">{activeRepoMeta.status_detail}</span>}
            </div>
          </div>
        ) : (
          <div className="repo-empty-state">Select a repository to begin operations.</div>
        )}
      </section>

      {activeRepo && (
        <ActiveFleetConsole repoPath={activeRepo} autonomousMode={autonomousMode} />
      )}

      {activeRepo && (
        <section className="agent-engagement-section">
          <div className="agent-tabs">
            <button 
              className={`agent-tab poe ${activeAgent === 'poe' ? 'active' : ''}`}
              onClick={() => setActiveAgent('poe')}
            >
              <div className="agent-icon">P</div>
              Product Poe
            </button>
            <button 
              className={`agent-tab thrawn ${activeAgent === 'thrawn' ? 'active' : ''}`}
              onClick={() => setActiveAgent('thrawn')}
            >
              <div className="agent-icon">T</div>
              Grand Admiral Thrawn
            </button>
            <button 
              className={`agent-tab vader ${activeAgent === 'vader' ? 'active' : ''}`}
              onClick={() => setActiveAgent('vader')}
            >
              <div className="agent-icon">V</div>
              Vibe Vader
            </button>
          </div>

          <div className="agent-content-area glass">
            {activeAgent === 'poe' && (
              <div className="agent-panel animate-in poe-theme">
                <div className="panel-header">
                  <h3>Product Management & Backlog</h3>
                  <p>Define user intents and manage the development queue.</p>
                </div>
                <PoeRoadmapBrief repoPath={activeRepo} />
                <QuickAddTask repoPath={activeRepo} onTaskAdded={fetchRepos} />
                <BacklogBoard repoPath={activeRepo} />
              </div>
            )}
            
            {activeAgent === 'thrawn' && (
              <div className="agent-panel animate-in thrawn-theme">
                <div className="panel-header">
                  <h3>Strategic Analysis & Intel</h3>
                  <p>Review architecture patterns and answer strategic questions.</p>
                </div>
                <ThrawnInteraction repoPath={activeRepo} />
              </div>
            )}

            {activeAgent === 'vader' && (
              <div className="agent-panel animate-in vader-theme">
                <div className="panel-header">
                  <h3>Action Queue & Interventions</h3>
                  <p>Review and unblock agents requiring human intervention.</p>
                </div>
                <ActionQueue repoPath={activeRepo} />
              </div>
            )}
          </div>
        </section>
      )}

      <style jsx>{`
        .dashboard-container {
          padding-top: 2rem;
          padding-bottom: 4rem;
          animation: fade-in 0.6s ease-out;
        }

        .page-header {
          text-align: center;
          margin-bottom: 3rem;
        }

        .page-header h1 {
          font-size: 2.8rem;
          margin-bottom: 0.5rem;
          background: linear-gradient(90deg, #fff, #aaa);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .subtitle {
          color: var(--text-secondary);
          font-size: 1.1rem;
        }

        .fleet-toggle-btn {
          padding: 0.8rem 1.5rem;
          border-radius: 20px;
          font-weight: bold;
          font-size: 1.1rem;
          cursor: pointer;
          border: 2px solid rgba(255, 255, 255, 0.2);
          background: rgba(0, 0, 0, 0.5);
          color: white;
          transition: all 0.3s ease;
        }

        .fleet-toggle-btn:hover {
          background: rgba(255, 255, 255, 0.1);
        }

        .fleet-toggle-btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
          transform: none;
        }

        .fleet-toggle-btn.active {
          background: rgba(74, 222, 128, 0.2);
          border-color: #4ade80;
          color: #4ade80;
          box-shadow: 0 0 15px rgba(74, 222, 128, 0.3);
        }

        .control-error {
          margin: 1rem auto 0;
          max-width: 620px;
        }

        .repo-selection-panel {
          display: flex;
          flex-direction: column;
          gap: 2rem;
          padding: 2rem;
          margin-bottom: 3rem;
          background: linear-gradient(135deg, rgba(20,20,20,0.8) 0%, rgba(10,10,10,0.9) 100%);
          border: 1px solid rgba(255, 255, 255, 0.1);
          box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
        }

        .repo-info h2 {
          font-size: 1.2rem;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 2px;
          margin-bottom: 1rem;
        }

        .repo-selector {
          display: flex;
          flex-wrap: wrap;
          gap: 1rem;
        }

        .repo-register {
          display: grid;
          grid-template-columns: minmax(220px, 1fr) auto;
          gap: 0.75rem;
          margin-top: 1rem;
        }

        .repo-register input {
          min-width: 0;
          background: rgba(0, 0, 0, 0.28);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 6px;
          color: #f9fafb;
          padding: 0.75rem 0.85rem;
        }

        .repo-register button {
          background: rgba(59, 130, 246, 0.16);
          border: 1px solid rgba(96, 165, 250, 0.45);
          border-radius: 6px;
          color: #bfdbfe;
          cursor: pointer;
          font-weight: 700;
          padding: 0.75rem 0.95rem;
        }

        .repo-register button:disabled {
          cursor: not-allowed;
          opacity: 0.55;
        }

        .repo-register-message {
          color: #cbd5e1;
          font-size: 0.82rem;
          margin-top: 0.55rem;
        }

        .repo-pill {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #eee;
          padding: 0.8rem 1.5rem;
          border-radius: 12px;
          font-size: 1rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }

        .repo-pill:hover {
          background: rgba(255, 255, 255, 0.1);
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }

        .repo-pill.active {
          background: var(--accent-color);
          border-color: var(--accent-color);
          color: white;
          box-shadow: 0 0 20px var(--accent-glow);
        }

        .repo-stats {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1.5rem;
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          padding-top: 2rem;
        }

        .stat-card {
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 12px;
          padding: 1.2rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
          transform: translateY(-2px);
          background: rgba(255,255,255,0.02);
        }

        .stat-label {
          font-size: 0.8rem;
          text-transform: uppercase;
          color: var(--text-secondary);
          letter-spacing: 1px;
        }

        .stat-value {
          font-size: 1.4rem;
          font-weight: 700;
          color: white;
        }

        .status-active {
          color: #4ade80;
          text-shadow: 0 0 10px rgba(74, 222, 128, 0.3);
        }

        .status-blocked-text {
          color: #fca5a5;
          text-shadow: 0 0 10px rgba(239, 68, 68, 0.25);
        }

        .stat-detail {
          color: var(--text-secondary);
          font-size: 0.78rem;
          line-height: 1.35;
        }

        .agent-engagement-section {
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }

        .agent-tabs {
          display: flex;
          gap: 1rem;
          justify-content: center;
          margin-bottom: 1rem;
        }

        .agent-tab {
          display: flex;
          align-items: center;
          gap: 0.8rem;
          background: rgba(25, 25, 25, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          padding: 1rem 2rem;
          border-radius: 16px;
          color: var(--text-secondary);
          font-weight: 600;
          font-size: 1.1rem;
          cursor: pointer;
          transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }

        .agent-icon {
          width: 32px;
          height: 32px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.1);
          font-weight: 800;
          font-size: 0.9rem;
        }

        .agent-tab:hover {
          background: rgba(40, 40, 40, 0.8);
          color: white;
          transform: translateY(-2px);
        }

        .agent-tab.active {
          background: rgba(255, 255, 255, 0.05);
          color: white;
          border-color: rgba(255, 255, 255, 0.2);
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        }

        .agent-tab.poe.active .agent-icon { background: #eab308; color: black; box-shadow: 0 0 15px rgba(234, 179, 8, 0.4); }
        .agent-tab.poe.active { border-color: rgba(234, 179, 8, 0.5); }

        .agent-tab.thrawn.active .agent-icon { background: #3b82f6; color: white; box-shadow: 0 0 15px rgba(59, 130, 246, 0.4); }
        .agent-tab.thrawn.active { border-color: rgba(59, 130, 246, 0.5); }

        .agent-tab.vader.active .agent-icon { background: #ef4444; color: white; box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }
        .agent-tab.vader.active { border-color: rgba(239, 68, 68, 0.5); }

        .agent-content-area {
          min-height: 500px;
          padding: 2.5rem;
          background: var(--card-bg);
          border: 1px solid rgba(255,255,255,0.05);
        }

        .panel-header {
          margin-bottom: 2rem;
          padding-bottom: 1rem;
          border-bottom: 1px solid rgba(255,255,255,0.1);
        }

        .panel-header h3 {
          font-size: 1.5rem;
          margin-bottom: 0.3rem;
          color: white;
        }

        .panel-header p {
          color: var(--text-secondary);
        }

        .animate-in {
          animation: slide-up 0.4s ease-out forwards;
        }

        @keyframes slide-up {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @keyframes fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        .error-banner {
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #fca5a5;
          padding: 1rem;
          border-radius: 12px;
          text-align: center;
          margin-bottom: 2rem;
        }

        .success-banner {
          background: rgba(34, 197, 94, 0.1);
          border: 1px solid rgba(34, 197, 94, 0.3);
          color: #86efac;
          padding: 1rem;
          border-radius: 12px;
          text-align: center;
          margin-bottom: 2rem;
        }

        @media (max-width: 768px) {
          .agent-tabs {
            flex-direction: column;
          }
          .agent-content-area {
            padding: 1.5rem;
          }
          .repo-info h2 {
             text-align: center;
          }
          .repo-selector {
             justify-content: center;
          }
        }
      `}</style>
    </div>
  );
}
