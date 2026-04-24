"use client";

import { useState, useEffect } from "react";
import { apiGet, apiPost } from "../app/api-client";

interface Question {
  question: string;
  answer: string | null;
}

interface ThrawnIntel {
  objective: string;
  architecture: string[];
  questions: Question[];
}

interface Props {
  repoPath: string;
}

export default function ThrawnInteraction({ repoPath }: Props) {
  const [intel, setIntel] = useState<ThrawnIntel | null>(null);
  const [loading, setLoading] = useState(true);
  const [objective, setObjective] = useState("");
  const [newQuestion, setNewQuestion] = useState("");
  const [status, setStatus] = useState<string | null>(null);

  const fetchIntel = async () => {
    try {
      setLoading(true);
      const data = await apiGet<ThrawnIntel>(`/thrawn/intel?repo_path=${encodeURIComponent(repoPath)}`);
      setIntel(data);
      setObjective(data.objective);
    } catch (err) {
      console.error("Failed to fetch Thrawn intel:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIntel();
  }, [repoPath]);

  const handleUpdateObjective = async () => {
    try {
      await apiPost("/thrawn/objective", { repo_path: repoPath, objective });
      setStatus("Objective updated!");
      setTimeout(() => setStatus(null), 3000);
      fetchIntel();
    } catch (err) {
      setStatus("Failed to update objective");
    }
  };

  const handleAnswerQuestion = async (question: string, answer: string) => {
    try {
      await apiPost("/thrawn/answer", { repo_path: repoPath, question, answer });
      setStatus("Answer submitted!");
      setTimeout(() => setStatus(null), 3000);
      fetchIntel();
    } catch (err) {
      setStatus("Failed to submit answer");
    }
  };

  const handleAskThrawn = async () => {
    if (!newQuestion.trim()) return;
    try {
      await apiPost("/thrawn/ask", { repo_path: repoPath, question: newQuestion });
      setNewQuestion("");
      setStatus("Question added for Thrawn!");
      setTimeout(() => setStatus(null), 3000);
      fetchIntel();
    } catch (err) {
      setStatus("Failed to add question");
    }
  };

  const handleTriggerThrawn = async () => {
    try {
      setStatus("Triggering Thrawn analysis...");
      await apiPost("/run-task", {
        repo_path: repoPath,
        agent_id: "thoughtful_thrawn",
        model: "gemini-2.0-flash", // Default or read from settings
        task_prompt: "Review the current intent and open questions. Generate new insights or questions if needed."
      });
      setStatus("Thrawn analysis started!");
      setTimeout(() => setStatus(null), 5000);
    } catch (err) {
      setStatus("Failed to trigger Thrawn");
    }
  };

  if (loading) return <div className="thrawn-loading">Loading Thrawn Intel...</div>;

  return (
    <div className="thrawn-container glass">
      <div className="thrawn-header">
        <div className="thrawn-title-row">
          <h2>Grand Admiral Thrawn</h2>
          <span className="badge-agent">Intel & Strategy</span>
        </div>
        <p className="thrawn-motto">"To defeat an enemy, you must know them."</p>
      </div>

      <div className="thrawn-section">
        <h3>Primary Objective</h3>
        <textarea 
          className="thrawn-input"
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          placeholder="What is the main goal of this repository?"
        />
        <button className="btn-small" onClick={handleUpdateObjective}>Update Objective</button>
      </div>

      <div className="thrawn-section">
        <h3>Architecture & Patterns</h3>
        <div className="arch-list">
          {intel?.architecture.map((pattern, idx) => (
            <div key={idx} className="arch-item">
              <span>{pattern}</span>
            </div>
          ))}
          <div className="a-input-row">
            <input 
              type="text" 
              placeholder="Add pattern (e.g. Hexagonal Architecture)..." 
              className="thrawn-input-small"
              onKeyDown={async (e) => {
                if (e.key === 'Enter') {
                  const val = (e.target as HTMLInputElement).value;
                  if (val) {
                    try {
                      await apiPost("/thrawn/architecture", { repo_path: repoPath, pattern: val });
                      (e.target as HTMLInputElement).value = "";
                      setStatus("Pattern added!");
                      setTimeout(() => setStatus(null), 3000);
                      fetchIntel();
                    } catch (err) {}
                  }
                }
              }}
            />
          </div>
        </div>
      </div>

      <div className="thrawn-section">
        <h3>Open Clarification Questions</h3>
        <div className="questions-list">
          {intel?.questions.map((q, idx) => (
            <div key={idx} className="question-item">
              <p className="q-text">{q.question}</p>
              {q.answer ? (
                <div className="a-bubble">
                  <span className="a-label">Answered:</span> {q.answer}
                </div>
              ) : (
                <div className="a-input-row">
                  <input 
                    type="text" 
                    placeholder="Your answer..." 
                    className="thrawn-input-small"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        handleAnswerQuestion(q.question, (e.target as HTMLInputElement).value);
                        (e.target as HTMLInputElement).value = "";
                      }
                    }}
                  />
                </div>
              )}
            </div>
          ))}
          {intel?.questions.length === 0 && <p className="no-items">No open questions. Fleet is clear.</p>}
        </div>
      </div>

      <div className="thrawn-section">
        <h3>Direct Interaction</h3>
        <div className="ask-row">
          <input 
            type="text" 
            value={newQuestion}
            onChange={(e) => setNewQuestion(e.target.value)}
            placeholder="Ask Thrawn a strategic question..." 
            className="thrawn-input-small"
          />
          <button className="btn-small" onClick={handleAskThrawn}>Ask</button>
        </div>
      </div>

      <div className="thrawn-footer">
        <button className="btn-primary btn-full" onClick={handleTriggerThrawn}>
          Trigger Strategic Review
        </button>
        {status && <p className="status-msg">{status}</p>}
      </div>

      <style jsx>{`
        .thrawn-container {
          margin-top: 2rem;
          padding: 1.5rem;
          border-left: 4px solid #4a90e2;
          background: rgba(10, 20, 40, 0.4);
        }
        .thrawn-header {
          margin-bottom: 1.5rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          padding-bottom: 1rem;
        }
        .thrawn-title-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .thrawn-title-row h2 {
          margin: 0;
          font-size: 1.2rem;
          color: #4a90e2;
          text-transform: uppercase;
          letter-spacing: 1px;
        }
        .thrawn-motto {
          font-style: italic;
          font-size: 0.8rem;
          color: #888;
          margin-top: 0.3rem;
        }
        .thrawn-section {
          margin-bottom: 1.5rem;
        }
        .thrawn-section h3 {
          font-size: 0.85rem;
          text-transform: uppercase;
          color: #aaa;
          margin-bottom: 0.8rem;
          letter-spacing: 0.5px;
        }
        .thrawn-input {
          width: 100%;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          color: white;
          padding: 0.8rem;
          font-size: 0.9rem;
          min-height: 80px;
          margin-bottom: 0.5rem;
          outline: none;
        }
        .thrawn-input:focus {
          border-color: #4a90e2;
        }
        .thrawn-input-small {
          flex: 1;
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 4px;
          color: white;
          padding: 0.5rem 0.8rem;
          font-size: 0.85rem;
          outline: none;
        }
        .questions-list {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .question-item {
          padding: 0.8rem;
          background: rgba(255, 255, 255, 0.03);
          border-radius: 6px;
        }
        .q-text {
          font-size: 0.9rem;
          margin: 0 0 0.5rem 0;
          color: #eee;
        }
        .a-bubble {
          font-size: 0.85rem;
          color: #4a90e2;
          background: rgba(74, 144, 226, 0.1);
          padding: 0.4rem 0.8rem;
          border-radius: 4px;
        }
        .a-label {
          font-weight: bold;
          margin-right: 0.4rem;
        }
        .arch-list {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .arch-item {
          font-size: 0.85rem;
          color: #ccc;
          padding: 0.3rem 0.6rem;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 4px;
          border-left: 2px solid #4a90e2;
        }
        .ask-row {
          display: flex;
          gap: 0.5rem;
        }
        .status-msg {
          font-size: 0.75rem;
          color: #4a90e2;
          margin-top: 0.8rem;
          text-align: center;
        }
        .no-items {
          font-size: 0.85rem;
          color: #666;
          text-align: center;
          padding: 1rem;
        }
        .badge-agent {
          font-size: 0.6rem;
          background: #4a90e2;
          color: white;
          padding: 2px 6px;
          border-radius: 3px;
        }
        .btn-full {
          width: 100%;
        }
      `}</style>
    </div>
  );
}
