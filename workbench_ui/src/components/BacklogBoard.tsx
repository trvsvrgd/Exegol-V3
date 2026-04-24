"use client";

import React, { useState, useEffect } from 'react';

interface Task {
    id: string;
    summary: string;
    priority: string;
    status: string;
    target_agent?: string;
    description?: string;
}

export default function BacklogBoard({ repoPath }: { repoPath: string }) {
    const [backlog, setBacklog] = useState<Task[]>([]);
    const [loading, setLoading] = useState(true);
    const [hideDone, setHideDone] = useState(true);

    const fetchBacklog = async () => {
        try {
            const res = await fetch(`http://localhost:8000/backlog?repo_path=${encodeURIComponent(repoPath)}`);
            if (!res.ok) throw new Error("Fetch failed");
            const data = await res.json();
            setBacklog(data);
            setLoading(false);
        } catch (err) {
            console.error("Backlog fetch error:", err);
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchBacklog();
    }, [repoPath]);

    const handleUpdate = async (taskId: string, updates: any) => {
        try {
            const res = await fetch('http://localhost:8000/backlog/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_path: repoPath, task_id: taskId, updates })
            });
            if (res.ok) fetchBacklog();
        } catch (err) {
            console.error(err);
        }
    };

    // Native Drag and Drop Implementation
    const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

    const onDragStart = (e: React.DragEvent, index: number) => {
        setDraggedIndex(index);
        e.dataTransfer.effectAllowed = "move";
    };

    const onDrop = async (e: React.DragEvent, index: number) => {
        if (draggedIndex === null || draggedIndex === index) return;

        const newBacklog = [...backlog];
        const [removed] = newBacklog.splice(draggedIndex, 1);
        newBacklog.splice(index, 0, removed);

        setBacklog(newBacklog);
        setDraggedIndex(null);

        // Persist the new order to the backend
        try {
            await fetch('http://localhost:8000/backlog/reorder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    repo_path: repoPath, 
                    task_ids: newBacklog.map(t => t.id) 
                })
            });
        } catch (err) {
            console.error("Failed to persist reorder:", err);
            fetchBacklog(); // Rollback on error
        }
    };

    const filtered = backlog.filter(t => 
        !hideDone || (t.status !== 'completed' && t.status !== 'done' && t.status !== 'failed')
    );

    if (loading) return <div style={{ color: '#888' }}>Accessing Backlog Records...</div>;

    return (
        <div className="backlog-container glass">
            <div className="backlog-header">
                <h3 className="title-glow" style={{ margin: 0 }}>Project Backlog</h3>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <label style={{ fontSize: '0.8rem', color: '#888', cursor: 'pointer', display: 'flex', gap: '0.5rem' }}>
                        <input type="checkbox" checked={hideDone} onChange={() => setHideDone(!hideDone)} />
                        Hide Completed
                    </label>
                    <span className="count-badge">{filtered.length} Tasks</span>
                </div>
            </div>

            <div className="task-list">
                {filtered.map((task, index) => (
                    <div 
                        key={task.id} 
                        className={`task-row ${draggedIndex === index ? 'dragging' : ''}`}
                        draggable
                        onDragStart={(e) => onDragStart(e, index)}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => onDrop(e, index)}
                    >
                        <div className="drag-handle">⋮⋮</div>
                        <div className="task-id">#{task.id.split('_').pop()}</div>
                        <div className="task-content">
                            <div className="task-summary">{task.summary}</div>
                            {task.target_agent && <div className="task-meta">{task.target_agent}</div>}
                        </div>
                        <div className="task-status">
                            <select 
                                value={task.status} 
                                onChange={(e) => handleUpdate(task.id, { status: e.target.value })}
                            >
                                <option value="todo">TODO</option>
                                <option value="in_progress">IN PROGRESS</option>
                                <option value="completed">COMPLETED</option>
                                <option value="failed">FAILED</option>
                                <option value="backlogged">BACKLOG</option>
                            </select>
                        </div>
                        <div className="task-priority">
                             <div className={`priority-tag ${task.priority}`}>{task.priority}</div>
                        </div>
                    </div>
                ))}
            </div>

            <style jsx>{`
                .backlog-container {
                    padding: 1.5rem;
                    display: flex;
                    flex-direction: column;
                    border-radius: 12px;
                }
                .backlog-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 1.5rem;
                    padding-bottom: 0.8rem;
                    border-bottom: 1px solid var(--border-color);
                }
                .count-badge {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 2px 8px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                }
                .task-list {
                    display: flex;
                    flex-direction: column;
                    gap: 0.5rem;
                }
                .task-row {
                    display: flex;
                    align-items: center;
                    gap: 1rem;
                    padding: 0.8rem 1rem;
                    background: rgba(0, 0, 0, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 6px;
                    cursor: move;
                    transition: all 0.2s;
                }
                .task-row:hover {
                    background: rgba(255, 255, 255, 0.05);
                    border-color: rgba(230, 0, 0, 0.2);
                }
                .task-row.dragging {
                    opacity: 0.5;
                    border: 1px dashed var(--accent-color);
                }
                .drag-handle {
                    color: #444;
                    font-weight: bold;
                    user-select: none;
                }
                .task-id {
                    font-family: monospace;
                    font-size: 0.75rem;
                    color: #555;
                    min-width: 50px;
                }
                .task-content {
                    flex: 1;
                }
                .task-summary {
                    font-size: 0.95rem;
                    font-weight: 500;
                }
                .task-meta {
                    font-size: 0.7rem;
                    color: var(--accent-color);
                    margin-top: 0.1rem;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                select {
                    background: #111;
                    color: #888;
                    border: 1px solid #333;
                    border-radius: 4px;
                    font-size: 0.7rem;
                    padding: 2px 4px;
                    cursor: pointer;
                }
                select:focus { outline: none; border-color: var(--accent-color); color: white; }
                .priority-tag {
                    font-size: 0.65rem;
                    padding: 2px 6px;
                    border-radius: 3px;
                    text-transform: uppercase;
                    background: #222;
                    color: #888;
                    text-align: center;
                    min-width: 60px;
                }
                .priority-tag.high { color: #ff5555; background: rgba(255, 85, 85, 0.1); }
                .priority-tag.medium { color: #ffaa00; background: rgba(255, 170, 0, 0.1); }
                .priority-tag.low { color: #55ff55; background: rgba(85, 255, 85, 0.1); }
            `}</style>
        </div>
    );
}
