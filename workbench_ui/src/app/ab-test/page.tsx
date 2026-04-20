"use client";

import { useState, useEffect } from "react";

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

  useEffect(() => {
    fetch("http://localhost:8000/repos")
      .then(res => res.json())
      .then(data => {
        setRepos(data);
        if (data.length > 0) setSelectedRepo(data[0].repo_path);
      });

    fetch("http://localhost:8000/agents")
      .then(res => res.json())
      .then(data => {
        setAgents(data);
        if (data.length > 0) setSelectedAgent(data[0].id);
      });
  }, []);

  const runTest = async () => {
    setLoading(true);
    setResults({});
    
    try {
      // Run Model A
      const resA = await fetch("http://localhost:8000/run-task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_path: selectedRepo,
          agent_id: selectedAgent,
          model: modelA,
          task_prompt: taskPrompt
        })
      });
      const dataA = await resA.json();

      // Run Model B
      const resB = await fetch("http://localhost:8000/run-task", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repo_path: selectedRepo,
          agent_id: selectedAgent,
          model: modelB,
          task_prompt: taskPrompt
        })
      });
      const dataB = await resB.json();

      setResults({ a: dataA, b: dataB });

      // Fetch Snapshots if hash is present
      if (dataA.snapshot_hash && dataB.snapshot_hash) {
        const snapA = await fetch(`http://localhost:8000/snapshots/${selectedAgent}_fleet_cycle?repo_path=${encodeURIComponent(selectedRepo)}`).then(r => r.json());
        const snapB = await fetch(`http://localhost:8000/snapshots/${selectedAgent}_fleet_cycle?repo_path=${encodeURIComponent(selectedRepo)}`).then(r => r.json());
        // Wait, the snapshot name depends on task_id. In Orchestrator it is "fleet_cycle" or "manual_go".
        // In DeveloperDexAgent: f"dex_{snapshot_data['task_id']}"
        // This is a bit inconsistent. Let's fix the API or the Agent to make snapshot retrieval easier.
      }
    } catch (error) {
      console.error("Test failed:", error);
      alert("Execution failed. Check if Backend API is running at :8000");
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
                <option key={r.repo_path} value={r.repo_path}>{r.repo_path.split('\\').pop()}</option>
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

        <div className="model-selectors" style={{ display: 'flex', gap: '2rem', marginTop: '2rem' }}>
          <div className="form-group" style={{ flex: 1 }}>
            <label className="title-glow">Brain A</label>
            <select value={modelA} onChange={e => setModelA(e.target.value)}>
              <option value="ollama">Ollama (Local)</option>
              <option value="gemini">Gemini (Cloud)</option>
            </select>
          </div>
          <div className="form-group" style={{ flex: 1 }}>
            <label className="title-glow">Brain B</label>
            <select value={modelB} onChange={e => setModelB(e.target.value)}>
              <option value="gemini">Gemini (Cloud)</option>
              <option value="ollama">Ollama (Local)</option>
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
      `}</style>
    </div>
  );
}

function DiffCard({ title, data }: { title: string, data: any }) {
  // Try to parse the summary if it's a string, or just use artifacts_written
  const actions = data.output_summary.split('\n').filter((l: string) => l.includes(':'));

  return (
    <div className="glass diff-card">
      <div className="card-header">
        <h3>{title}</h3>
        <span className="badge">{data.outcome}</span>
      </div>
      
      <div className="section-title">Planned Intelligence</div>
      <div className="action-list">
        {actions.length > 0 ? actions.map((action: string, i: number) => {
          const [type, status] = action.split(':');
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
      <pre className="summary-pre">{data.output_summary}</pre>
      
      <div className="card-footer">
        <span>Steps Used: {data.steps_used}</span>
        <span>ID: {data.session_id}</span>
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
