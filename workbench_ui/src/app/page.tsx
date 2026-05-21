"use client";

import { useState, useEffect, useCallback } from "react";
import ActionQueue from "../components/ActionQueue";
import BacklogBoard from "../components/BacklogBoard";
import QuickAddTask from "../components/QuickAddTask";
import ThrawnInteraction from "../components/ThrawnInteraction";
import ActiveFleetConsole from "../components/ActiveFleetConsole";

import { apiGet, apiPost } from "../app/api-client";

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
  repo_path?: string | null;
}

interface SupervisorHealth {
  status: "ok" | "degraded";
  checked_at: string;
  degraded_services: string[];
  degraded_repositories: string[];
}

export default function Home() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [activeRepo, setActiveRepo] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [activeAgent, setActiveAgent] = useState<'poe' | 'thrawn' | 'vader'>('poe');
  const [autonomousMode, setAutonomousMode] = useState<boolean>(false);
  const [cycleRunning, setCycleRunning] = useState<boolean>(false);
  const [controlBusy, setControlBusy] = useState<boolean>(false);
  const [controlError, setControlError] = useState<string | null>(null);
  const [controlMessage, setControlMessage] = useState<string | null>(null);
  const [supervisorHealth, setSupervisorHealth] = useState<SupervisorHealth | null>(null);

  useEffect(() => {
    async function fetchAutonomousStatus() {
      try {
        const data = await apiGet<AutonomousStatus>("/fleet/autonomous-status");
        setAutonomousMode(data.continuous_mode);
        setCycleRunning(data.cycle_running);
      } catch (e) {
        console.error("Failed to fetch autonomous status", e);
      }
    }
    fetchAutonomousStatus();
    const interval = setInterval(fetchAutonomousStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    async function fetchSupervisorHealth() {
      try {
        const data = await apiGet<SupervisorHealth>("/fleet/supervisor-health");
        setSupervisorHealth(data);
      } catch (e) {
        console.error("Failed to fetch supervisor health", e);
      }
    }
    fetchSupervisorHealth();
    const interval = setInterval(fetchSupervisorHealth, 15000);
    return () => clearInterval(interval);
  }, []);

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
      setControlMessage(enabled ? "Autonomous fleet loop started." : "Autonomous fleet loop stopped.");
    } catch (e) {
      console.error("Failed to toggle autonomous mode", e);
      setControlError("Fleet control request failed. Check backend logs.");
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
      setControlMessage("Autonomous fleet loop started for the selected repository.");
    } catch (e) {
      console.error("Failed to run autonomous fleet", e);
      setControlError("Fleet run request failed. Check backend logs.");
    } finally {
      setControlBusy(false);
    }
  };

  const fetchRepos = useCallback(async () => {
    try {
      const data = await apiGet<Repo[]>("/repos");
      setRepos(data);
      if (data.length > 0 && !activeRepo) {
        setActiveRepo(data[0].repo_path);
      }
    } catch (err) {
      console.error("Failed to fetch repos:", err);
      setFetchError("Unable to load repository list. Check backend connectivity.");
    }
  }, [activeRepo]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchRepos();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [fetchRepos]);

  const activeRepoMeta = repos.find((repo) => repo.repo_path === activeRepo);

  return (
    <div className="container dashboard-container">
      <header className="page-header">
        <h1 className="title-glow">Exegol Command Center</h1>
        <p className="subtitle">Select your target repository and engage with the agent fleet.</p>
        <div className="fleet-controls" style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'center', gap: '1rem' }}>
          <button
            className="fleet-toggle-btn"
            onClick={autonomousMode ? () => setAutonomousFleet(false) : runAutonomousFleet}
            disabled={controlBusy || (!autonomousMode && (cycleRunning || !activeRepo))}
            title={autonomousMode ? "Stop the autonomous fleet loop." : cycleRunning ? "A fleet cycle is already running." : "Run the autonomous fleet for the selected repository."}
          >
            {cycleRunning ? "Fleet Running" : autonomousMode ? "Stop Autonomous Fleet" : "Run Autonomous Fleet"}
          </button>
        </div>
        {controlError && <div className="error-banner control-error">{controlError}</div>}
        {controlMessage && <div className="success-banner control-error">{controlMessage}</div>}
        {supervisorHealth?.status === "degraded" && (
          <div className="error-banner control-error">
            Needs attention:
            {" "}
            {[
              ...supervisorHealth.degraded_services,
              ...supervisorHealth.degraded_repositories.map((repo) => repo.split(/[/\\]/).filter(Boolean).slice(-1)[0]),
            ].join(", ")}
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
                  onClick={() => setActiveRepo(repo.repo_path)}
                  title={repo.repo_path}
                >
                  {label}
                </button>
              );
            })}
          </div>
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
