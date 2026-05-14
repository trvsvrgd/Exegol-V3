"use client";

import { useState, useEffect } from "react";
import { apiGet, apiPost } from "../api-client";

interface Repo {
  repo_path: string;
  model_routing_preference: string;
}

interface Agent {
  id: string;
  name: string;
}

export default function ABTestPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [selectedAgent, setSelectedAgent] = useState("");
  const [modelA, setModelA] = useState("ollama");
  const [modelB, setModelB] = useState("gemini");
  const [taskPrompt, setTaskPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<{a?: any, b?: any}>({});
  const [localModels, setLocalModels] = useState<any[]>([]);

  useEffect(() => {
    apiGet<Repo[]>("/repos")
      .then(data => {
        setRepos(data);
        if (data.length > 0) setSelectedRepo(data[0].repo_path);
      })
      .catch(err => console.error("Failed to fetch repos:", err));

    apiGet<Agent[]>("/agents")
      .then(data => {
        setAgents(data);
        if (data.length > 0) setSelectedAgent(data[0].id);
      })
      .catch(err => console.error("Failed to fetch agents:", err));

    apiGet<any[]>("/local-models")
      .then(data => setLocalModels(data))
      .catch(err => console.error("Local models fetch error", err));
  }, []);

  const pollTask = async (sessionId: string) => {
    let attempts = 0;
    const maxAttempts = 100; // ~5 minutes with 3s interval
    
    while (attempts < maxAttempts) {
      try {
        const statusData = await apiGet<any>(`/task-status/${sessionId}`);
        if (statusData.status === "done") {
          return statusData.result;
        }
        if (statusData.status === "error") {
          return {
            outcome: "failure",
            output_summary: "Execution failed on backend.",
            errors: statusData.result?.errors || ["Unknown backend error"],
            session_id: sessionId
          };
        }
      } catch (err) {
        console.error(`Polling error for ${sessionId}:`, err);
      }
      
      await new Promise(resolve => setTimeout(resolve, 3000));
      attempts++;
    }
    return { 
      outcome: "timeout", 
      output_summary: "Task timed out after 5 minutes.", 
      session_id: sessionId 
    };
  };

  const runTest = async () => {
    setLoading(true);
    setResults({});
    
    try {
      // 1. Submit both tasks to get session IDs
      const submitA = await apiPost<any>("/run-task", {
        repo_path: selectedRepo,
        agent_id: selectedAgent,
        model: modelA,
        task_prompt: taskPrompt
      });

      const submitB = await apiPost<any>("/run-task", {
        repo_path: selectedRepo,
        agent_id: selectedAgent,
        model: modelB,
        task_prompt: taskPrompt
      });

      // 2. Poll for both results in parallel
      const [dataA, dataB] = await Promise.all([
        pollTask(submitA.session_id),
        pollTask(submitB.session_id)
      ]);

      setResults({ a: dataA, b: dataB });

      // 3. Fetch Snapshots if hashes are present
      if (dataA?.snapshot_hash && dataB?.snapshot_hash) {
        await apiGet(`/snapshots/${selectedAgent}_fleet_cycle?repo_path=${encodeURIComponent(selectedRepo)}`);
        await apiGet(`/snapshots/${selectedAgent}_fleet_cycle?repo_path=${encodeURIComponent(selectedRepo)}`);
      }
    } catch (error) {
      console.error("Test failed:", error);
      alert("Execution failed. Check if Backend API is running and your API Key is correct.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <header style={{ marginBottom: '3rem' }}>
        <h1 className="title-glow">A/B Testing Lab</h1>
        <p style={{ color: '#888' }}>Compare how different brains interpret the same mission.</p>
      </header>

      <section className="glass" style={{ padding: '2rem', marginBottom: '3rem' }}>
        <div className="grid-form">
          <div className="form-group">
            <label>Target Repository</label>
            <select value={selectedRepo} onChange={e => setSelectedRepo(e.target.value)}>
              {repos.map(r => (
                <option key={r.repo_path} value={r.repo_path}>
                  {r.repo_path.split(/[/\\]/).filter(Boolean).pop()}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Agent Selection</label>
            <select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)}>
              {agents.map(a => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="task-input" style={{ marginTop: '2rem' }}>
          <label>Task Prompt</label>
          <textarea 
            placeholder="Describe the task for the agent..." 
            value={taskPrompt}
            onChange={e => setTaskPrompt(e.target.value)}
          />
        </div>

        <div className="model-selectors">
          <div className="form-group" style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="title-glow">Brain A</label>
              <button 
                onClick={() => apiGet<any[]>("/local-models").then(setLocalModels)}
                style={{ background: 'none', border: 'none', color: '#555', fontSize: '0.6rem', cursor: 'pointer', textTransform: 'uppercase' }}
              >
                ↻ Refresh Models
              </button>
            </div>
            <select value={modelA} onChange={e => setModelA(e.target.value)}>
              <option value="ollama">Ollama (Auto-Detect)</option>
              <option value="gemini">Gemini 1.5 Pro</option>
              <option value="claude">Claude 3.5 Sonnet</option>
              {localModels.length > 0 && (
                <optgroup label="Installed Local Models">
                  {localModels.map(m => (
                    <option key={m.name} value={m.name}>{m.name}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>
          <div className="form-group" style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="title-glow">Brain B</label>
            </div>
            <select value={modelB} onChange={e => setModelB(e.target.value)}>
              <option value="gemini">Gemini 1.5 Pro</option>
              <option value="ollama">Ollama (Auto-Detect)</option>
              <option value="claude">Claude 3.5 Sonnet</option>
              {localModels.length > 0 && (
                <optgroup label="Installed Local Models">
                  {localModels.map(m => (
                    <option key={m.name} value={m.name}>{m.name}</option>
                  ))}
                </optgroup>
              )}
            </select>
          </div>
        </div>

        <button 
          className="btn-primary glow-red" 
          style={{ marginTop: '2rem', width: '100%' }}
          onClick={runTest}
          disabled={loading}
        >
          {loading ? "Engaging Engines..." : "Initiate Dual Execution"}
        </button>
      </section>

      {results.a && (
        <section className="results-grid">
          <DiffCard title={`Brain A: ${modelA.toUpperCase()}`} data={results.a} />
          <DiffCard title={`Brain B: ${modelB.toUpperCase()}`} data={results.b} />
        </section>
      )}

      <style jsx>{`
        .grid-form {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 2rem;
        }
        .model-selectors {
          display: flex;
          gap: 2rem;
          margin-top: 2rem;
        }
        .form-group label {
          display: block;
          margin-bottom: 0.5rem;
          font-size: 0.8rem;
          text-transform: uppercase;
          color: #888;
        }
        select, textarea {
          width: 100%;
          background: rgba(40, 40, 40, 0.5);
          border: 1px solid #333;
          color: white;
          padding: 12px;
          border-radius: 6px;
          font-size: 1rem;
        }
        textarea {
          height: 120px;
          resize: vertical;
        }
        .results-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 2rem;
          margin-top: 3rem;
        }

        @media (max-width: 850px) {
          .grid-form, .results-grid {
            grid-template-columns: 1fr;
          }
          .model-selectors {
            flex-direction: column;
            gap: 1.5rem;
          }
        }
      `}</style>
    </div>
  );
}

function DiffCard({ title, data }: { title: string, data: any }) {
  // Try to parse the summary if it's a string, or just use artifacts_written
  const outputSummary = data?.output_summary || "";
  const actions = outputSummary.split('\n').filter((l: string) => l.includes(':'));

  return (
    <div className="glass diff-card">
      <div className="card-header">
        <h3>{title}</h3>
        <span className="badge">{data?.outcome || "PENDING"}</span>
      </div>
      
      <div className="section-title">Planned Intelligence</div>
      <div className="action-list">
        {actions.length > 0 ? actions.map((action: string, i: number) => {
          const parts = action.split(':');
          const type = parts[0] || "";
          const isWrite = type.toLowerCase().includes('write');
          return (
            <div key={i} className="action-item">
              <span className={`type-tag ${isWrite ? 'write' : 'replace'}`}>
                {isWrite ? 'NEW' : 'MOD'}
              </span>
              <span className="action-text">{action}</span>
            </div>
          );
        }) : (
          <div className="empty-state">No file actions recorded.</div>
        )}
      </div>

      <div className="section-title" style={{ marginTop: '1.5rem' }}>Final Log</div>
      <pre className="summary-pre">{outputSummary || "No output summary available."}</pre>
      
      <div className="card-footer">
        <span>Steps Used: {data?.steps_used || 0}</span>
        <span>ID: {data?.session_id || "N/A"}</span>
      </div>

      <style jsx>{`
        .diff-card {
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 2rem;
          border-bottom: 1px solid rgba(255,0,0,0.1);
          padding-bottom: 1rem;
        }
        .badge {
          background: rgba(230, 0, 0, 0.1);
          color: var(--accent-color);
          padding: 4px 10px;
          border-radius: 4px;
          font-size: 0.7rem;
          text-transform: uppercase;
          font-weight: 700;
        }
        .section-title {
          font-size: 0.75rem;
          text-transform: uppercase;
          color: #555;
          letter-spacing: 1px;
          margin-bottom: 1rem;
          font-weight: 800;
        }
        .action-list {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .action-item {
          display: flex;
          align-items: center;
          gap: 1rem;
          background: rgba(255,255,255,0.03);
          padding: 10px;
          border-radius: 6px;
          border-left: 3px solid #333;
        }
        .type-tag {
          font-size: 0.6rem;
          font-weight: 800;
          padding: 2px 6px;
          border-radius: 3px;
        }
        .type-tag.write { background: #004d00; color: #00ff00; }
        .type-tag.replace { background: #4d3300; color: #ffaa00; }
        .action-text {
          font-size: 0.85rem;
          color: #ccc;
          font-family: monospace;
        }
        .summary-pre {
          background: #000;
          padding: 1rem;
          border-radius: 6px;
          font-size: 0.8rem;
          color: #aaa;
          overflow-x: auto;
          white-space: pre-wrap;
          max-height: 200px;
          overflow-y: auto;
        }
        .card-footer {
          margin-top: auto;
          padding-top: 1.5rem;
          display: flex;
          justify-content: space-between;
          font-size: 0.7rem;
          color: #444;
        }
        .empty-state {
          font-size: 0.8rem;
          color: #444;
          font-style: italic;
        }
      `}</style>
    </div>
  );
}
