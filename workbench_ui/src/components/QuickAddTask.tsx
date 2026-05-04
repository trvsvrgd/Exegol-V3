"use client";

import { useState } from 'react';
import { apiPost } from '../app/api-client';

export default function QuickAddTask({ repoPath, onTaskAdded }: { repoPath: string, onTaskAdded: () => void }) {
    const [summary, setSummary] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!summary.trim() || isSubmitting) return;

        setIsSubmitting(true);
        try {
            await apiPost('/backlog/add', { repo_path: repoPath, summary });
            setSummary("");
            onTaskAdded();
        } catch (err) {
            console.error("Failed to add task:", err);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="quick-add glass">
            <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem' }}>
                <input 
                    type="text" 
                    value={summary}
                    onChange={(e) => setSummary(e.target.value)}
                    placeholder="Describe a new User Intent or task..."
                    disabled={isSubmitting}
                />
                <button type="submit" className="btn-primary" disabled={isSubmitting || !summary.trim()}>
                    {isSubmitting ? "..." : "Add Task"}
                </button>
            </form>

            <style jsx>{`
                .quick-add {
                    padding: 1rem;
                    margin-bottom: 2rem;
                    border-left: 3px solid var(--accent-color);
                }
                input {
                    flex: 1;
                    background: rgba(0, 0, 0, 0.4);
                    border: 1px solid var(--border-color);
                    border-radius: 6px;
                    color: white;
                    padding: 0.8rem 1rem;
                    font-size: 0.95rem;
                    transition: border-color 0.3s;
                }
                input:focus {
                    outline: none;
                    border-color: var(--accent-color);
                }
                .btn-primary {
                    white-space: nowrap;
                    font-size: 0.8rem;
                }
            `}</style>
        </div>
    );
}
