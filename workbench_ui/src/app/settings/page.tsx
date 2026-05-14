"use client";

import { useState, useEffect } from "react";

import { apiGet, apiPost } from "../api-client";

interface Agent {
    id: string;
    name: string;
    wake_word: string;
}

export default function Settings() {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [mappings, setMappings] = useState<Record<string, string>>({});
    const [localModels, setLocalModels] = useState<any[]>([]);
    const [apiKeyStatus, setApiKeyStatus] = useState<Record<string, boolean>>({ gemini: true, claude: true });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        const loadData = async () => {
            try {
                const [agentsData, mappingsData, modelsData, keysData] = await Promise.all([
                    apiGet<Agent[]>("/agents"),
                    apiGet<Record<string, string>>("/agent-models"),
                    apiGet<any[]>("/local-models"),
                    apiGet<Record<string, boolean>>("/api-keys/status")
                ]);
                setAgents(agentsData);
                setMappings(mappingsData);
                setLocalModels(modelsData);
                setApiKeyStatus(keysData);
            } catch (err) {
                console.error("Settings load error", err);
            }
        };
        loadData();
    }, []);

    const saveSettings = async () => {
        setSaving(true);
        try {
            await apiPost("/agent-models", { 
                mappings: Object.entries(mappings).map(([id, model]) => ({ agent_id: id, model }))
            });
            alert("Configuration synchronized with Exegol backend.");
        } catch (err) {
            console.error(err);
            alert("Sync failed.");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="container">
            <header style={{ marginBottom: '2rem' }}>
                <a href="/" style={{ color: 'var(--accent-color)', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span>←</span> Return to Fleet Command
                </a>
                <h1 className="title-glow" style={{ marginTop: '1.5rem', fontSize: '2.5rem' }}>Agent Settings</h1>
                <p style={{ color: 'var(--text-secondary)' }}>Manage the neural distribution and model routing for the Exegol fleet.</p>
            </header>

            <div className="glass settings-card glow-red">
                <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)', background: 'rgba(255,0,0,0.05)' }}>
                    <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Model Routing Matrix</h3>
                    <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: '#666' }}>Assign local or cloud brains to specific agents. Changes take effect on the next wake word trigger.</p>
                </div>
                
                <table className="settings-table">
                    <thead>
                        <tr>
                            <th>Agent Identifier</th>
                            <th>Wake Word</th>
                            <th>Neural Model Allocation</th>
                        </tr>
                    </thead>
                    <tbody>
                        {agents.map(agent => {
                            const selectedModel = mappings[agent.id] || "ollama";
                            const isMissingKey = (selectedModel === "gemini" && !apiKeyStatus.gemini) || 
                                               (selectedModel === "claude" && !apiKeyStatus.claude);
                            
                            return (
                                <tr key={agent.id}>
                                    <td style={{ fontWeight: 600 }}>{agent.id}</td>
                                    <td><code style={{ background: 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.1)' }}>{agent.wake_word}</code></td>
                                    <td>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                            <select 
                                                value={selectedModel} 
                                                onChange={(e) => setMappings({...mappings, [agent.id]: e.target.value})}
                                                className={`model-select ${isMissingKey ? 'warning-border' : ''}`}
                                            >
                                                <option value="ollama">Ollama (Auto-Detect)</option>
                                                <option value="gemini">Gemini 1.5 Pro {!apiKeyStatus.gemini ? " (⚠️ No API Key)" : ""}</option>
                                                <option value="claude">Claude 3.5 Sonnet {!apiKeyStatus.claude ? " (⚠️ No API Key)" : ""}</option>
                                                {localModels.length > 0 && (
                                                    <optgroup label="Installed Local Models">
                                                        {localModels.map(m => (
                                                            <option key={m.name} value={m.name}>{m.name}</option>
                                                        ))}
                                                    </optgroup>
                                                )}
                                            </select>
                                            {isMissingKey && (
                                                <span style={{ color: '#ff4444', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                                    <span style={{ fontSize: '1rem' }}>⚠️</span> 
                                                    Missing API Key. Execution will fail.
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
                
                <div className="settings-footer">
                    <button className="btn-primary" onClick={saveSettings} disabled={saving}>
                        {saving ? "🔄 Synchronizing..." : "⚡ Save Allocation Config"}
                    </button>
                </div>
            </div>

            <style jsx>{`
                .settings-card {
                    border-radius: 12px;
                    overflow: hidden;
                    animation: fadeIn 0.5s ease-out;
                }
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .settings-table {
                    width: 100%;
                    border-collapse: collapse;
                }
                th {
                    text-align: left;
                    padding: 1rem 1.5rem;
                    background: rgba(255, 255, 255, 0.02);
                    color: var(--text-secondary);
                    font-size: 0.75rem;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }
                td {
                    padding: 1.2rem 1.5rem;
                    border-bottom: 1px solid var(--border-color);
                    font-size: 0.9rem;
                }
                tr:last-child td {
                    border-bottom: none;
                }
                .model-select {
                    background: #111;
                    color: white;
                    border: 1px solid #333;
                    padding: 8px 12px;
                    border-radius: 6px;
                    width: 100%;
                    max-width: 250px;
                    font-size: 0.85rem;
                    cursor: pointer;
                    transition: border-color 0.3s;
                }
                .model-select:focus {
                    outline: none;
                    border-color: var(--accent-color);
                }
                .warning-border {
                    border-color: #ff4444 !important;
                    box-shadow: 0 0 5px rgba(255, 68, 68, 0.3);
                }
                .settings-footer {
                    padding: 1.5rem;
                    border-top: 1px solid var(--border-color);
                    text-align: right;
                    background: rgba(0,0,0,0.2);
                }
                .btn-primary {
                    min-width: 220px;
                }
            `}</style>
        </div>
    );
}
