"use client";

import { useState, useEffect } from "react";
import { apiGet } from "../api-client";

const REPO_PATH = process.env.NEXT_PUBLIC_REPO_PATH || "";

interface ToolEntry {
  id: string;
  description: string;
  risk: string;
  category: string;
  agents: string[];
  usage_count: number;
}

export default function ToolRegistryPage() {
  const [tools, setTools] = useState<ToolEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  const fetchTools = () => {
    apiGet<ToolEntry[]>(`/fleet/tools?repo_path=${encodeURIComponent(REPO_PATH)}`)
      .then(data => {
        setTools(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch tool registry:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchTools();
  }, []);

  const filteredTools = tools.filter(tool => 
    tool.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
    tool.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    tool.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getRiskColor = (risk: string) => {
    switch (risk.toLowerCase()) {
      case 'critical': return '#ff4757';
      case 'high': return '#ffa502';
      case 'medium': return '#eccc68';
      case 'low': return '#2ed573';
      default: return '#747d8c';
    }
  };

  if (loading) return <div className="loading">Syncing Tool Registry...</div>;

  return (
    <div className="tools-page">
      <header className="tools-header">
        <h1 className="title-glow">Global Tool Registry</h1>
        <p className="subtitle">Observability into agent capabilities, risk exposure, and usage frequency.</p>
      </header>

      <section className="search-bar">
        <input 
          type="text" 
          placeholder="Search tools, categories, or descriptions..." 
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="glass-input"
        />
      </section>

      <section className="tools-grid">
        {filteredTools.map(tool => (
          <div key={tool.id} className="tool-card glass">
            <div className="tool-header">
              <div className="tool-id">
                <h3>{tool.id}</h3>
                <span className="category-tag">{tool.category}</span>
              </div>
              <div 
                className="risk-badge" 
                style={{ backgroundColor: `${getRiskColor(tool.risk)}22`, color: getRiskColor(tool.risk), borderColor: getRiskColor(tool.risk) }}
              >
                {tool.risk}
              </div>
            </div>
            
            <p className="description">{tool.description}</p>
            
            <div className="tool-usage">
              <span className="usage-label">Fleet Usage (30d)</span>
              <span className="usage-value">{tool.usage_count}</span>
            </div>

            <div className="tool-owners">
              <span className="owners-label">Authorized Agents</span>
              <div className="owners-list">
                {tool.agents.map(agent => (
                  <span key={agent} className="agent-tag">{agent}</span>
                ))}
                {tool.agents.length === 0 && <span className="no-owners">None</span>}
              </div>
            </div>
          </div>
        ))}
      </section>

      <style jsx>{`
        .tools-page {
          padding: 3rem;
          min-height: 100vh;
          background: linear-gradient(to bottom, #070707, #111111);
          color: #eaeaea;
        }
        .tools-header {
          margin-bottom: 3rem;
        }
        .subtitle {
          color: #888;
          opacity: 0.7;
          margin-top: 0.5rem;
          font-size: 1.1rem;
        }
        .search-bar {
          margin-bottom: 3rem;
        }
        .glass-input {
          width: 100%;
          padding: 1.25rem 2rem;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          color: #fff;
          font-size: 1.1rem;
          outline: none;
          transition: all 0.3s ease;
        }
        .glass-input:focus {
          background: rgba(255, 255, 255, 0.05);
          border-color: #4dabf7;
          box-shadow: 0 0 20px rgba(77, 171, 247, 0.15);
        }
        .tools-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
          gap: 2rem;
        }
        .tool-card {
          padding: 2rem;
          border-radius: 16px;
          background: rgba(25, 25, 25, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          backdrop-filter: blur(10px);
          display: flex;
          flex-direction: column;
          transition: all 0.3s ease;
        }
        .tool-card:hover {
          background: rgba(30, 30, 30, 0.8);
          transform: translateY(-5px);
          border-color: rgba(255, 255, 255, 0.15);
        }
        .tool-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 1.5rem;
        }
        .tool-id h3 {
          margin: 0;
          font-size: 1.2rem;
          color: #fff;
          letter-spacing: 1px;
        }
        .category-tag {
          font-size: 0.7rem;
          color: #666;
          text-transform: uppercase;
          letter-spacing: 1px;
        }
        .risk-badge {
          font-size: 0.65rem;
          text-transform: uppercase;
          font-weight: 800;
          padding: 4px 10px;
          border-radius: 20px;
          border: 1px solid;
          letter-spacing: 1px;
        }
        .description {
          font-size: 0.95rem;
          color: #bbb;
          line-height: 1.6;
          margin-bottom: 1.5rem;
          flex-grow: 1;
        }
        .tool-usage {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1rem 0;
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          margin-bottom: 1.5rem;
        }
        .usage-label {
          font-size: 0.75rem;
          color: #666;
          text-transform: uppercase;
        }
        .usage-value {
          font-size: 1.2rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
          color: #4dabf7;
        }
        .owners-label {
          display: block;
          font-size: 0.75rem;
          color: #666;
          text-transform: uppercase;
          margin-bottom: 1rem;
        }
        .owners-list {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem;
        }
        .agent-tag {
          font-size: 0.7rem;
          background: rgba(77, 171, 247, 0.1);
          color: #4dabf7;
          padding: 4px 8px;
          border-radius: 4px;
        }
        .no-owners {
          color: #444;
          font-style: italic;
          font-size: 0.9rem;
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
      `}</style>
    </div>
  );
}
