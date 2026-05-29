"use client";

import { useEffect } from "react";
import Link from "next/link";

interface ErrorBoundaryProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: ErrorBoundaryProps) {
  useEffect(() => {
    // Log the error to console or telemetry service
    console.error("Caught global rendering crash:", error);
  }, [error]);

  return (
    <div className="error-boundary-container">
      <div className="error-card glass">
        <div className="error-icon-wrapper">
          <span className="error-icon">⚡</span>
        </div>
        <h2 className="error-title">Control Tower Disruption</h2>
        <p className="error-subtitle">
          An unexpected runtime rendering crash occurred inside the Control Tower frontend.
          This is typically caused by malformed API payloads or missing state properties.
        </p>

        {error.message && (
          <div className="error-details">
            <strong>System Diagnostics:</strong>
            <pre className="error-code">{error.message}</pre>
            {error.digest && <span className="digest-code">Diagnostic Digest: <code>{error.digest}</code></span>}
          </div>
        )}

        <div className="button-group">
          <button onClick={() => reset()} className="btn-primary">
            ↺ Recover View
          </button>
          <Link href="/" className="btn-secondary">
            ← Return to Tower
          </Link>
        </div>
      </div>

      <style jsx>{`
        .error-boundary-container {
          min-height: 70vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2rem;
          background: linear-gradient(135deg, #07070a 0%, #101018 100%);
          color: #eaeaea;
          font-family: 'Inter', 'Segoe UI', sans-serif;
        }

        .error-card {
          max-width: 580px;
          width: 100%;
          padding: 3rem 2.5rem;
          border-radius: 16px;
          background: rgba(20, 20, 30, 0.4);
          border: 1px solid rgba(239, 68, 68, 0.18);
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.6), 0 0 30px rgba(239, 68, 68, 0.05);
          text-align: center;
          backdrop-filter: blur(16px);
        }

        .error-icon-wrapper {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 64px;
          height: 64px;
          border-radius: 50%;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.25);
          color: #ef4444;
          font-size: 2rem;
          margin-bottom: 1.5rem;
          box-shadow: 0 0 15px rgba(239, 68, 68, 0.2);
        }

        .error-title {
          font-size: 1.8rem;
          font-weight: 800;
          color: #fff;
          margin-bottom: 0.75rem;
          letter-spacing: -0.5px;
          background: linear-gradient(90deg, #fff, #fca5a5);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .error-subtitle {
          font-size: 0.95rem;
          line-height: 1.6;
          color: #9ca3af;
          margin-bottom: 2rem;
        }

        .error-details {
          text-align: left;
          background: rgba(0, 0, 0, 0.4);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          padding: 1.2rem;
          margin-bottom: 2rem;
        }

        .error-details strong {
          display: block;
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 1px;
          color: #ef4444;
          margin-bottom: 0.5rem;
        }

        .error-code {
          margin: 0;
          font-family: 'JetBrains Mono', 'Fira Code', monospace;
          font-size: 0.8rem;
          color: #f87171;
          white-space: pre-wrap;
          word-break: break-word;
          line-height: 1.4;
        }

        .digest-code {
          display: block;
          margin-top: 0.5rem;
          font-size: 0.72rem;
          color: #6b7280;
        }

        .digest-code code {
          background: rgba(255, 255, 255, 0.08);
          padding: 1px 4px;
          border-radius: 4px;
          color: #aaa;
        }

        .button-group {
          display: flex;
          gap: 1rem;
          justify-content: center;
        }

        .btn-primary {
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #fca5a5;
          padding: 0.75rem 1.5rem;
          border-radius: 8px;
          font-size: 0.9rem;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .btn-primary:hover {
          background: rgba(239, 68, 68, 0.25);
          color: #fff;
          border-color: #ef4444;
          box-shadow: 0 0 15px rgba(239, 68, 68, 0.15);
        }

        .btn-secondary {
          background: rgba(255, 255, 255, 0.05);
          border: 1px solid rgba(255, 255, 255, 0.1);
          color: #d1d5db;
          padding: 0.75rem 1.5rem;
          border-radius: 8px;
          font-size: 0.9rem;
          font-weight: 700;
          text-decoration: none;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.1);
          color: #fff;
          border-color: rgba(255, 255, 255, 0.25);
        }
      `}</style>
    </div>
  );
}
