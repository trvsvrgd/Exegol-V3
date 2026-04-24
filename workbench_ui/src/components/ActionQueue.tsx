"use client";

import React, { useState, useEffect } from 'react';

interface ActionItem {
    id: string;
    task: string;
    category: string;
    context: string;
    status: string;
    notes: string;
    timestamp: string;
}

export default function ActionQueue({ repoPath }: { repoPath: string }) {
    const [queue, setQueue] = useState<ActionItem[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchQueue = async () => {
        try {
            const res = await fetch(`http://localhost:8000/human-queue?repo_path=${encodeURIComponent(repoPath)}`);
            if (!res.ok) throw new Error("Failed to fetch");
            const data = await res.json();
            setQueue(data);
            setLoading(false);
        } catch (err) {
            console.error("Failed to fetch human queue:", err);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchQueue();
    }, [repoPath]);

    const handleAction = async (itemId: string, action: string, notes?: string) => {
        try {
            await fetch('http://localhost:8000/human-queue/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_path: repoPath, action, item_id: itemId, notes })
            });
            fetchQueue();
        } catch (err) {
            console.error(`Failed to perform action ${action}:`, err);
        }
    };

    if (loading) return <div style={{ padding: '1rem', color: '#888' }}>Accessing Vibe Vader Queue...</div>;

    const activeCount = queue.filter(i => i.status !== 'done').length;

    return (
        <div className="action-queue glass">
            <div className="queue-header">
                <h3 className="title-glow" style={{ margin: 0, fontSize: '1.2rem' }}>Vibe Vader Queue</h3>
                <span className="badge">{activeCount} Pending Intervention</span>
            </div>
            
            {queue.length === 0 ? (
                <p style={{ padding: '1rem', color: '#555', fontSize: '0.9rem' }}>No boundary-crossing items detected. The fleet is autonomous for now.</p>
            ) : (
                <div className="queue-items">
                    {queue.map(item => (
                        <div key={item.id} className={`queue-item ${item.status === 'done' ? 'done' : ''}`}>
                            <div className="item-main">
                                <div className="checkbox-container" onClick={() => handleAction(item.id, item.status === 'done' ? 'pending' : 'done')}>
                                    <div className={`custom-checkbox ${item.status === 'done' ? 'checked' : ''}`} />
                                </div>
                                <div className="item-content">
                                    <div className="item-task">{item.task}</div>
                                    <div className="item-context">{item.context}</div>
                                </div>
                                <button className="dismiss-btn" onClick={() => handleAction(item.id, 'dismiss')} title="Dismiss Item">
                                    &times;
                                </button>
                            </div>
                            <div className="item-notes">
                                <textarea 
                                    placeholder="Append human observations..." 
                                    defaultValue={item.notes}
                                    onBlur={(e) => handleAction(item.id, 'update_notes', e.target.value)}
                                />
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <style jsx>{`
                .action-queue {
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                    border-radius: 12px;
                }
                .queue-header {
                    padding: 1rem 1.5rem;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-bottom: 1px solid var(--border-color);
                    background: rgba(230, 0, 0, 0.05);
                }
                .badge {
                    background: var(--accent-color);
                    color: white;
                    padding: 2px 10px;
                    border-radius: 12px;
                    font-size: 0.7rem;
                    font-weight: bold;
                    letter-spacing: 0.5px;
                }
                .queue-items {
                    flex: 1;
                    overflow-y: auto;
                    padding: 1rem;
                }
                .queue-item {
                    margin-bottom: 1rem;
                    padding: 1rem;
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    transition: all 0.3s ease;
                }
                .queue-item:hover {
                    background: rgba(255, 255, 255, 0.05);
                    border-color: rgba(230, 0, 0, 0.3);
                }
                .queue-item.done {
                    opacity: 0.4;
                    filter: grayscale(0.8);
                }
                .item-main {
                    display: flex;
                    gap: 1rem;
                    align-items: flex-start;
                    margin-bottom: 0.8rem;
                }
                .checkbox-container {
                    padding-top: 2px;
                    cursor: pointer;
                }
                .custom-checkbox {
                    width: 18px;
                    height: 18px;
                    border: 1.5px solid var(--accent-color);
                    border-radius: 4px;
                    position: relative;
                    transition: all 0.2s;
                }
                .custom-checkbox.checked {
                    background: var(--accent-color);
                }
                .custom-checkbox.checked::after {
                    content: '✓';
                    position: absolute;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    color: white;
                    font-size: 11px;
                }
                .item-content {
                    flex: 1;
                }
                .item-task {
                    font-weight: 600;
                    font-size: 0.95rem;
                    color: var(--text-primary);
                    margin-bottom: 0.2rem;
                }
                .item-context {
                    font-size: 0.8rem;
                    color: var(--text-secondary);
                    line-height: 1.4;
                }
                .dismiss-btn {
                    background: none;
                    border: none;
                    color: #555;
                    font-size: 1.5rem;
                    line-height: 1;
                    cursor: pointer;
                    transition: color 0.2s;
                    padding: 0 4px;
                }
                .dismiss-btn:hover {
                    color: var(--accent-color);
                }
                .item-notes {
                    border-top: 1px solid rgba(255, 255, 255, 0.05);
                    padding-top: 0.8rem;
                }
                textarea {
                    width: 100%;
                    background: rgba(0, 0, 0, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 4px;
                    color: #aaa;
                    padding: 0.5rem;
                    font-size: 0.8rem;
                    min-height: 40px;
                    resize: vertical;
                    transition: all 0.2s;
                }
                textarea:focus {
                    outline: none;
                    border-color: var(--accent-color);
                    color: var(--text-primary);
                    background: rgba(0, 0, 0, 0.4);
                }
            `}</style>
        </div>
    );
}
