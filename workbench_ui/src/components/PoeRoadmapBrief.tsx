"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../app/api-client";

interface RoadmapItem {
  text: string;
  evidence: string;
  source_id?: string;
}

interface RoadmapBrief {
  schema_version: number;
  owner_agent: string;
  updated_at: string;
  freshness: string;
  objective: {
    goal: string;
    phase: string;
    status: string;
    loop_count: number;
    blocked_reason: string | null;
  };
  current_focus: string;
  accomplished: RoadmapItem[];
  mvp: {
    summary: string;
    status: string;
    success_criteria: string[];
    constraints: string[];
  };
  long_term: RoadmapItem[];
}

interface PoeRoadmapBriefProps {
  repoPath: string;
}

function formatEvidence(value: string): string {
  return value.replace(/_/g, " ");
}

function formatUpdated(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toLocaleString();
}

export default function PoeRoadmapBrief({ repoPath }: PoeRoadmapBriefProps) {
  const [brief, setBrief] = useState<RoadmapBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBrief = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiGet<RoadmapBrief>(`/poe/roadmap?repo_path=${encodeURIComponent(repoPath)}`);
      setBrief(data);
      setError(null);
    } catch (err) {
      console.error("Failed to load Poe roadmap brief:", err);
      setError("Roadmap brief unavailable.");
    } finally {
      setLoading(false);
    }
  }, [repoPath]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void fetchBrief();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [fetchBrief]);

  if (loading) {
    return <section className="roadmap-brief loading">Loading Poe roadmap...</section>;
  }

  if (error) {
    return <section className="roadmap-brief error">{error}</section>;
  }

  if (!brief) return null;

  const isFallback = brief.freshness !== "poe_refreshed";
  const isBlocked = brief.objective.status === "blocked" || brief.mvp.status === "blocked";
  const isEmpty = brief.mvp.status === "not_defined"
    && brief.accomplished.length === 0
    && brief.long_term.length === 0;
  const statusLabel = isBlocked
    ? "Blocked"
    : isFallback
      ? "Computed"
      : brief.mvp.status.replace(/_/g, " ");

  if (isEmpty) {
    return (
      <section className="roadmap-brief empty">
        <div className="brief-header">
          <div>
            <span className="eyebrow">Product Poe</span>
            <h3>Poe Roadmap Brief</h3>
          </div>
          <span className="status-pill">Not Defined</span>
        </div>
        <p>No MVP roadmap has been captured for this repository yet.</p>
        <style jsx>{styles}</style>
      </section>
    );
  }

  return (
    <section className={`roadmap-brief ${isBlocked ? "blocked" : ""} ${isFallback ? "fallback" : ""}`}>
      <div className="brief-header">
        <div>
          <span className="eyebrow">Product Poe</span>
          <h3>Poe Roadmap Brief</h3>
        </div>
        <div className="brief-meta">
          <span className="updated">Updated {formatUpdated(brief.updated_at)}</span>
          <span className="status-pill">{statusLabel}</span>
        </div>
      </div>

      <div className="focus-row">
        <span>Current Focus</span>
        <strong>{brief.current_focus}</strong>
      </div>

      <div className="brief-grid">
        <div className="brief-column">
          <h4>Accomplished</h4>
          {brief.accomplished.length === 0 ? (
            <p className="muted">No verified completed work yet.</p>
          ) : (
            <ul>
              {brief.accomplished.map((item, index) => (
                <li key={`${item.text}-${index}`}>
                  <span>{item.text}</span>
                  <em>{formatEvidence(item.evidence)}</em>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="brief-column mvp-column">
          <h4>MVP</h4>
          <p className="mvp-summary">{brief.mvp.summary}</p>
          {brief.mvp.success_criteria.length > 0 && (
            <ul>
              {brief.mvp.success_criteria.map((item) => (
                <li key={item}>
                  <span>{item}</span>
                  <em>objective</em>
                </li>
              ))}
            </ul>
          )}
          {brief.mvp.constraints.length > 0 && (
            <div className="constraints">
              {brief.mvp.constraints.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          )}
        </div>

        <div className="brief-column">
          <h4>Long-Term</h4>
          {brief.long_term.length === 0 ? (
            <p className="muted">No post-MVP slices captured yet.</p>
          ) : (
            <ul>
              {brief.long_term.map((item, index) => (
                <li key={`${item.text}-${index}`}>
                  <span>{item.text}</span>
                  <em>{formatEvidence(item.evidence)}</em>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {brief.objective.blocked_reason && (
        <div className="blocked-reason">
          <span>Blocker</span>
          <strong>{brief.objective.blocked_reason}</strong>
        </div>
      )}

      <style jsx>{styles}</style>
    </section>
  );
}

const styles = `
  .roadmap-brief {
    border: 1px solid rgba(234, 179, 8, 0.24);
    border-radius: 8px;
    background: rgba(17, 17, 17, 0.72);
    margin-bottom: 1.25rem;
    padding: 1.1rem;
  }

  .roadmap-brief.loading,
  .roadmap-brief.error,
  .roadmap-brief.empty {
    color: #cbd5e1;
  }

  .roadmap-brief.error {
    border-color: rgba(239, 68, 68, 0.3);
    color: #fca5a5;
  }

  .roadmap-brief.blocked {
    border-color: rgba(239, 68, 68, 0.38);
  }

  .roadmap-brief.fallback {
    border-style: dashed;
  }

  .brief-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.9rem;
  }

  .eyebrow {
    color: #facc15;
    display: block;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    margin-bottom: 0.2rem;
    text-transform: uppercase;
  }

  h3,
  h4,
  p {
    margin: 0;
  }

  h3 {
    color: #f8fafc;
    font-size: 1.15rem;
  }

  h4 {
    color: #e5e7eb;
    font-size: 0.82rem;
    letter-spacing: 0.06em;
    margin-bottom: 0.65rem;
    text-transform: uppercase;
  }

  .brief-meta {
    align-items: flex-end;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .updated {
    color: #94a3b8;
    font-size: 0.72rem;
  }

  .status-pill {
    background: rgba(234, 179, 8, 0.15);
    border: 1px solid rgba(234, 179, 8, 0.36);
    border-radius: 999px;
    color: #fde68a;
    font-size: 0.72rem;
    font-weight: 800;
    padding: 0.22rem 0.55rem;
    text-transform: capitalize;
    white-space: nowrap;
  }

  .blocked .status-pill {
    background: rgba(239, 68, 68, 0.14);
    border-color: rgba(239, 68, 68, 0.4);
    color: #fecaca;
  }

  .focus-row {
    background: rgba(0, 0, 0, 0.28);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    display: grid;
    gap: 0.25rem;
    margin-bottom: 0.95rem;
    padding: 0.75rem;
  }

  .focus-row span,
  .blocked-reason span {
    color: #94a3b8;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .focus-row strong,
  .blocked-reason strong {
    color: #f8fafc;
    font-size: 0.92rem;
    line-height: 1.35;
  }

  .brief-grid {
    display: grid;
    gap: 0.85rem;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .brief-column {
    min-width: 0;
  }

  .mvp-column {
    border-left: 1px solid rgba(255, 255, 255, 0.08);
    border-right: 1px solid rgba(255, 255, 255, 0.08);
    padding: 0 0.85rem;
  }

  .mvp-summary {
    color: #f8fafc;
    font-size: 0.9rem;
    line-height: 1.35;
    margin-bottom: 0.55rem;
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: 0.48rem;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  li {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  li span {
    color: #d1d5db;
    font-size: 0.84rem;
    line-height: 1.35;
    overflow-wrap: anywhere;
  }

  li em {
    color: #94a3b8;
    font-size: 0.68rem;
    font-style: normal;
    text-transform: uppercase;
  }

  .constraints {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.6rem;
  }

  .constraints span {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 999px;
    color: #cbd5e1;
    font-size: 0.7rem;
    padding: 0.25rem 0.45rem;
  }

  .muted {
    color: #94a3b8;
    font-size: 0.82rem;
  }

  .blocked-reason {
    background: rgba(127, 29, 29, 0.24);
    border: 1px solid rgba(239, 68, 68, 0.24);
    border-radius: 6px;
    display: grid;
    gap: 0.25rem;
    margin-top: 0.95rem;
    padding: 0.75rem;
  }

  @media (max-width: 860px) {
    .brief-grid {
      grid-template-columns: 1fr;
    }

    .mvp-column {
      border-left: none;
      border-right: none;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 0.85rem 0;
    }
  }

  @media (max-width: 620px) {
    .brief-header {
      flex-direction: column;
    }

    .brief-meta {
      align-items: flex-start;
    }
  }
`;
