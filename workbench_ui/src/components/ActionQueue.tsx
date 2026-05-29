"use client";

import { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from '../app/api-client';

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
    const [observationNotes, setObservationNotes] = useState<Record<string, string>>({});

    const fetchQueue = useCallback(async () => {
        try {
            const data = await apiGet<ActionItem[]>(`/human-queue?repo_path=${encodeURIComponent(repoPath)}`);
            setQueue(Array.isArray(data) ? data : []);
            setLoading(false);
        } catch (err) {
            console.error("Failed to fetch human queue:", err);
            setLoading(false);
        }
    }, [repoPath]);

    useEffect(() => {
        const timeout = window.setTimeout(() => {
            void fetchQueue();
        }, 0);
        return () => window.clearTimeout(timeout);
    }, [fetchQueue]);

    const handleAction = async (itemId: string, action: string, notes?: string) => {
        try {
            await apiPost('/human-queue/action', { repo_path: repoPath, action, item_id: itemId, notes });
            fetchQueue();
        } catch (err) {
            console.error(`Failed to perform action ${action}:`, err);
        }
    };

    const getCategoryLabel = (category: string) => {
        switch (category.toLowerCase()) {
            case 'intent': return 'Strategic Intent';
            case 'onboarding': return 'Project Onboarding';
            case 'technical_debt': return 'Technical Debt';
            case 'refactor': return 'Code Refactoring';
            case 'eval':
            case 'evaluation': return 'Execution Evaluation';
            case 'security': return 'Security Alert';
            default: return category.charAt(0).toUpperCase() + category.slice(1);
        }
    };

    const getCategoryColor = (category: string) => {
        switch (category.toLowerCase()) {
            case 'intent': return '#4a90e2';
            case 'onboarding': return '#10b981';
            case 'technical_debt': return '#f59e0b';
            case 'refactor': return '#8b5cf6';
            case 'eval':
            case 'evaluation': return '#ec4899';
            case 'security': return '#ef4444';
            default: return '#6b7280';
        }
    };

    const getWhyExplanation = (category: string) => {
        switch (category.toLowerCase()) {
            case 'intent':
                return "Vibe Vader flagged this because a core project objective, structural decision, or design direction is missing or ambiguous. Clear intent is required for the fleet to proceed safely.";
            case 'onboarding':
                return "During initial fleet onboarding, high-level project boundaries and developer rules must be confirmed by a human commander.";
            case 'technical_debt':
            case 'refactor':
                return "Technical debt (e.g. mock code, unimplemented stubs, or low-quality patterns) was detected in the workspace. Vader has quarantined this boundary violation.";
            case 'eval':
            case 'evaluation':
                return "A deterministic check or execution benchmark failed. Human intervention is required to verify if the output is acceptable or needs redirection.";
            case 'security':
                return "Potential security exposure, credentials leak, or unsafe network access attempted by code generator components.";
            default:
                return "A workspace boundary audit flagged this item, requiring human oversight to preserve fleet integrity.";
        }
    };

    const getActionInstructions = (category: string) => {
        switch (category.toLowerCase()) {
            case 'intent':
            case 'onboarding':
                return "Review the question/context, type your response in the resolution field below, and click 'Resolve & Close' to update the fleet's trajectory.";
            case 'technical_debt':
            case 'refactor':
                return "Examine the referenced code or file. If you have addressed the technical debt, describe how you fixed it and click 'Resolve & Close'. If it should be handled automatically, you can click 'Dismiss' to route it to Developer Dex.";
            case 'security':
                return "Mitigate the security concern immediately. Document the resolution and click 'Resolve & Close'.";
            default:
                return "Complete the requested task, describe your action/observations in the field below, and click 'Resolve & Close'.";
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
                    {queue.map(item => {
                        const isDone = item.status === 'done';
                        const notesValue = observationNotes[item.id] !== undefined ? observationNotes[item.id] : (item.notes || "");

                        return (
                            <div key={item.id} className={`queue-item ${isDone ? 'done' : ''}`}>
                                <div className="item-header">
                                    <span className="category-badge" style={{ backgroundColor: getCategoryColor(item.category) }}>
                                        {getCategoryLabel(item.category)}
                                    </span>
                                    <span className="timestamp">
                                        {item.timestamp ? new Date(item.timestamp).toLocaleString() : 'Recent Audit'}
                                    </span>
                                </div>
                                
                                <div className="item-body">
                                    <div className="item-task">{item.task}</div>
                                    <div className="item-context-box">
                                        <span className="label-prefix">Context:</span> {item.context}
                                    </div>
                                    
                                    {!isDone && (
                                        <div className="audit-details">
                                            <div className="detail-section">
                                                <strong>Why is this in the backlog?</strong>
                                                <p>{getWhyExplanation(item.category)}</p>
                                            </div>
                                            <div className="detail-section">
                                                <strong>Action Required:</strong>
                                                <p>{getActionInstructions(item.category)}</p>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="item-action-area">
                                    {isDone ? (
                                        <div className="resolved-banner">
                                            <div className="resolved-text">
                                                <strong>Resolved:</strong> {item.notes || 'Task marked complete.'}
                                            </div>
                                            <button 
                                                className="btn-reopen" 
                                                onClick={() => handleAction(item.id, 'pending', item.notes)}
                                            >
                                                Reopen Task
                                            </button>
                                        </div>
                                    ) : (
                                        <div className="resolution-form">
                                            <textarea 
                                                placeholder="Detail how you resolved this (e.g. 'Refactored utils.py and verified tests')..." 
                                                value={notesValue}
                                                onChange={(e) => {
                                                    const val = e.target.value;
                                                    setObservationNotes(prev => ({ ...prev, [item.id]: val }));
                                                }}
                                            />
                                            <div className="button-group">
                                                <button 
                                                    className="btn-resolve"
                                                    onClick={() => handleAction(item.id, 'done', notesValue)}
                                                    disabled={!notesValue.trim()}
                                                >
                                                    Resolve & Close
                                                </button>
                                                <button 
                                                    className="btn-dismiss"
                                                    onClick={() => handleAction(item.id, 'dismiss')}
                                                    title="Dismiss/Ignore Task"
                                                >
                                                    Dismiss
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
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
                    padding: 1.2rem;
                    background: rgba(255, 255, 255, 0.02);
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    transition: all 0.3s ease;
                }
                .queue-item:hover {
                    background: rgba(255, 255, 255, 0.04);
                    border-color: rgba(230, 0, 0, 0.25);
                }
                .queue-item.done {
                    opacity: 0.6;
                    border-color: rgba(16, 185, 129, 0.2);
                }
                .item-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 0.8rem;
                }
                .category-badge {
                    color: white;
                    padding: 2px 8px;
                    border-radius: 4px;
                    font-size: 0.65rem;
                    font-weight: 700;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                .timestamp {
                    font-size: 0.7rem;
                    color: #777;
                }
                .item-body {
                    margin-bottom: 1rem;
                }
                .item-task {
                    font-weight: 600;
                    font-size: 1rem;
                    color: var(--text-primary);
                    margin-bottom: 0.4rem;
                }
                .item-context-box {
                    font-size: 0.8rem;
                    color: #ccc;
                    background: rgba(0, 0, 0, 0.2);
                    padding: 0.6rem;
                    border-radius: 6px;
                    margin-top: 0.4rem;
                    border-left: 2px solid #ef4444;
                    line-height: 1.4;
                }
                .label-prefix {
                    font-weight: 700;
                    color: #aaa;
                    margin-right: 0.2rem;
                }
                .audit-details {
                    margin-top: 0.8rem;
                    display: flex;
                    flex-direction: column;
                    gap: 0.6rem;
                    background: rgba(239, 68, 68, 0.02);
                    border: 1px dashed rgba(239, 68, 68, 0.15);
                    border-radius: 6px;
                    padding: 0.75rem;
                }
                .detail-section {
                    font-size: 0.75rem;
                    line-height: 1.35;
                }
                .detail-section strong {
                    color: #ef4444;
                    display: block;
                    margin-bottom: 0.2rem;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                .detail-section p {
                    margin: 0;
                    color: #aaa;
                }
                .item-action-area {
                    margin-top: 0.8rem;
                }
                .resolved-banner {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    background: rgba(16, 185, 129, 0.08);
                    border: 1px solid rgba(16, 185, 129, 0.2);
                    padding: 0.6rem 0.8rem;
                    border-radius: 6px;
                    gap: 1rem;
                }
                .resolved-text {
                    font-size: 0.8rem;
                    color: #10b981;
                    line-height: 1.4;
                }
                .resolution-form {
                    display: flex;
                    flex-direction: column;
                    gap: 0.6rem;
                }
                textarea {
                    width: 100%;
                    background: rgba(0, 0, 0, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 4px;
                    color: #ddd;
                    padding: 0.5rem 0.8rem;
                    font-size: 0.8rem;
                    min-height: 50px;
                    resize: vertical;
                    transition: all 0.2s;
                }
                textarea:focus {
                    outline: none;
                    border-color: var(--accent-color);
                    color: var(--text-primary);
                    background: rgba(0, 0, 0, 0.4);
                }
                .button-group {
                    display: flex;
                    gap: 0.5rem;
                }
                .btn-resolve {
                    background: rgba(239, 68, 68, 0.15) !important;
                    color: #ef4444 !important;
                    border: 1px solid rgba(239, 68, 68, 0.25) !important;
                    padding: 0.4rem 1rem;
                    border-radius: 4px;
                    font-size: 0.8rem;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                .btn-resolve:hover:not(:disabled) {
                    background: rgba(239, 68, 68, 0.25) !important;
                    color: #ff6b6b !important;
                }
                .btn-resolve:disabled {
                    opacity: 0.4;
                    cursor: not-allowed;
                }
                .btn-reopen {
                    background: rgba(255, 255, 255, 0.05) !important;
                    color: #aaa !important;
                    border: 1px solid rgba(255, 255, 255, 0.1) !important;
                    padding: 0.3rem 0.6rem;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    cursor: pointer;
                    white-space: nowrap;
                    transition: all 0.2s;
                }
                .btn-reopen:hover {
                    background: rgba(255, 255, 255, 0.1) !important;
                    color: #fff !important;
                }
                .btn-dismiss {
                    background: rgba(255, 255, 255, 0.05) !important;
                    color: #aaa !important;
                    border: 1px solid rgba(255, 255, 255, 0.1) !important;
                    padding: 0.4rem 0.8rem;
                    border-radius: 4px;
                    font-size: 0.8rem;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                .btn-dismiss:hover {
                    background: rgba(239, 68, 68, 0.1) !important;
                    color: #ef4444 !important;
                    border-color: rgba(239, 68, 68, 0.2) !important;
                }
            `}</style>
        </div>
    );
}
