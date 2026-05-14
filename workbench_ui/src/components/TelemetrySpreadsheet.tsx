"use client";

import { useState, useEffect, useMemo } from "react";
import { apiGet } from "../app/api-client";

interface TelemetrySpreadsheetProps {
  isOpen: boolean;
  onClose: () => void;
  repoPath: string;
  dataType: "backlog" | "hitl" | "interactions" | "success" | "total_tasks" | null;
}

export default function TelemetrySpreadsheet({
  isOpen,
  onClose,
  repoPath,
  dataType
}: TelemetrySpreadsheetProps) {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: "asc" | "desc" } | null>(null);
  const [filterText, setFilterText] = useState("");

  useEffect(() => {
    if (isOpen && dataType && repoPath) {
      fetchData();
    }
  }, [isOpen, dataType, repoPath]);

  const fetchData = async () => {
    setLoading(true);
    try {
      let endpoint = "";
      let fetchedData: any[] = [];
      
      if (dataType === "backlog") {
        endpoint = `/backlog?repo_path=${encodeURIComponent(repoPath)}`;
        fetchedData = await apiGet<any[]>(endpoint);
      } else if (dataType === "hitl") {
        endpoint = `/human-queue?repo_path=${encodeURIComponent(repoPath)}`;
        fetchedData = await apiGet<any[]>(endpoint);
      } else if (dataType === "interactions" || dataType === "success" || dataType === "total_tasks") {
        endpoint = `/fleet/interactions?repo_path=${encodeURIComponent(repoPath)}`;
        fetchedData = await apiGet<any[]>(endpoint);
        
        if (dataType === "success") {
          // Pre-filter for successes vs failures, wait, if they clicked "Success" they might want to see both, or just success?
          // Let's just show all and maybe pre-sort or just leave it for them to filter.
          // The prompt said: "successes and failures". So we will just show interactions.
        }
      }

      setData(Array.isArray(fetchedData) ? fetchedData : []);
    } catch (err) {
      console.error("Failed to fetch spreadsheet data:", err);
      setData([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (key: string) => {
    let direction: "asc" | "desc" = "asc";
    if (sortConfig && sortConfig.key === key && sortConfig.direction === "asc") {
      direction = "desc";
    }
    setSortConfig({ key, direction });
  };

  // Determine columns dynamically based on data
  const columns = useMemo(() => {
    if (data.length === 0) return [];
    
    // Define preferred column order for known types
    if (dataType === "backlog") {
      return ["id", "status", "priority", "summary", "target_agent", "created_at"];
    } else if (dataType === "hitl") {
      return ["id", "status", "action_required", "created_at"];
    } else {
      return ["timestamp", "agent_id", "outcome", "steps_used", "duration_seconds", "task_summary"];
    }
  }, [data, dataType]);

  const filteredAndSortedData = useMemo(() => {
    let result = [...data];

    // Filter
    if (filterText) {
      const lowerFilter = filterText.toLowerCase();
      result = result.filter(item => 
        Object.values(item).some(val => 
          String(val).toLowerCase().includes(lowerFilter)
        )
      );
    }

    // Sort
    if (sortConfig) {
      result.sort((a, b) => {
        const aVal = a[sortConfig.key];
        const bVal = b[sortConfig.key];
        
        if (aVal < bVal) return sortConfig.direction === "asc" ? -1 : 1;
        if (aVal > bVal) return sortConfig.direction === "asc" ? 1 : -1;
        return 0;
      });
    }

    return result;
  }, [data, filterText, sortConfig]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content glass" onClick={e => e.stopPropagation()}>
        <header className="modal-header">
          <div className="header-titles">
            <h2>Telemetry Data: {dataType?.toUpperCase()}</h2>
            <p className="subtitle">Repository: {repoPath}</p>
          </div>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </header>

        <div className="toolbar">
          <input 
            type="text" 
            placeholder="Filter data..." 
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="filter-input"
          />
          <span className="record-count">{filteredAndSortedData.length} records found</span>
        </div>

        <div className="table-container">
          {loading ? (
            <div className="loading-state">Loading data...</div>
          ) : filteredAndSortedData.length === 0 ? (
            <div className="empty-state">No data available.</div>
          ) : (
            <table className="telemetry-table">
              <thead>
                <tr>
                  {columns.map(col => (
                    <th key={col} onClick={() => handleSort(col)} className="sortable-header">
                      {col.replace(/_/g, ' ').toUpperCase()}
                      {sortConfig?.key === col && (
                        <span className="sort-icon">{sortConfig.direction === "asc" ? " ▲" : " ▼"}</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredAndSortedData.map((row, idx) => (
                  <tr key={row.id || row.session_id || idx}>
                    {columns.map(col => (
                      <td key={col} title={String(row[col])}>
                        {typeof row[col] === 'object' ? JSON.stringify(row[col]) : String(row[col] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <style jsx>{`
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.85);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 2rem;
        }
        .modal-content {
          width: 100%;
          max-width: 1200px;
          height: 80vh;
          background: #0f0f0f;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .modal-header {
          padding: 1.5rem 2rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          background: rgba(255,255,255,0.02);
        }
        .header-titles h2 {
          margin: 0;
          font-size: 1.5rem;
          color: #fff;
          letter-spacing: 1px;
        }
        .subtitle {
          margin: 0.25rem 0 0 0;
          font-size: 0.8rem;
          color: #888;
        }
        .close-btn {
          background: none;
          border: none;
          color: #888;
          font-size: 2rem;
          cursor: pointer;
          line-height: 1;
          transition: color 0.2s;
        }
        .close-btn:hover { color: #fff; }
        .toolbar {
          padding: 1rem 2rem;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .filter-input {
          background: #1a1a1a;
          border: 1px solid #333;
          color: #eee;
          padding: 0.5rem 1rem;
          border-radius: 6px;
          font-size: 0.9rem;
          width: 300px;
        }
        .record-count {
          color: #888;
          font-size: 0.9rem;
        }
        .table-container {
          flex: 1;
          overflow: auto;
          position: relative;
        }
        .telemetry-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
        }
        .telemetry-table th {
          position: sticky;
          top: 0;
          background: #1a1a1a;
          padding: 1rem;
          font-size: 0.75rem;
          text-transform: uppercase;
          color: #aaa;
          letter-spacing: 1px;
          cursor: pointer;
          border-bottom: 1px solid #333;
          z-index: 10;
        }
        .telemetry-table th:hover {
          background: #252525;
        }
        .telemetry-table td {
          padding: 0.75rem 1rem;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          font-size: 0.85rem;
          color: #ccc;
          max-width: 250px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .telemetry-table tr:hover td {
          background: rgba(255, 255, 255, 0.02);
        }
        .sortable-header {
          user-select: none;
        }
        .sort-icon {
          margin-left: 0.5rem;
          color: #4dabf7;
        }
        .loading-state, .empty-state {
          padding: 4rem;
          text-align: center;
          color: #555;
          font-style: italic;
        }
      `}</style>
    </div>
  );
}
