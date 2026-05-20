"""
model_benchmark_db.py — Model Benchmark Database
==================================================
SQLite-backed database of AI model benchmarks across multiple factors.
Scores are normalized 0-100. Updated weekly by ModelRouterMothmaAgent.
"""

import os
import json
import sqlite3
import datetime
from typing import List, Dict, Any, Optional

DB_NAME = "model_benchmarks.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    -- Capability scores (0-100, higher is better)
    coding_score INTEGER DEFAULT 0,
    agentic_score INTEGER DEFAULT 0,
    reasoning_score INTEGER DEFAULT 0,
    speed_score INTEGER DEFAULT 0,
    image_gen_score INTEGER DEFAULT 0,
    video_gen_score INTEGER DEFAULT 0,
    multilingual_score INTEGER DEFAULT 0,
    -- Cost & availability
    cost_input_per_1m REAL DEFAULT 0.0,
    cost_output_per_1m REAL DEFAULT 0.0,
    cost_score INTEGER DEFAULT 0,
    ollama_available INTEGER DEFAULT 0,
    ollama_model_name TEXT DEFAULT '',
    context_window INTEGER DEFAULT 0,
    -- Metadata
    tier TEXT DEFAULT 'mid',
    notes TEXT DEFAULT '',
    source TEXT DEFAULT 'web_research',
    assessed_at TEXT NOT NULL,
    UNIQUE(model_name, provider)
);
"""

# Seed data based on May 2026 research
SEED_DATA = [
    # --- Frontier models ---
    {"model_name": "Claude Opus 4.7", "provider": "Anthropic", "tier": "frontier",
     "coding_score": 97, "agentic_score": 95, "reasoning_score": 98, "speed_score": 45,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 85,
     "cost_input_per_1m": 5.0, "cost_output_per_1m": 25.0, "cost_score": 15,
     "ollama_available": 0, "context_window": 200000,
     "notes": "Top SWE-bench. Best for multi-file refactoring & complex reasoning."},
    {"model_name": "Claude Sonnet 4.6", "provider": "Anthropic", "tier": "mid",
     "coding_score": 90, "agentic_score": 88, "reasoning_score": 90, "speed_score": 70,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 82,
     "cost_input_per_1m": 3.0, "cost_output_per_1m": 15.0, "cost_score": 35,
     "ollama_available": 0, "context_window": 200000,
     "notes": "Best daily-driver for coding. Strong balance of cost and capability."},
    {"model_name": "Claude 4.5 Haiku", "provider": "Anthropic", "tier": "efficient",
     "coding_score": 72, "agentic_score": 65, "reasoning_score": 70, "speed_score": 92,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 75,
     "cost_input_per_1m": 0.8, "cost_output_per_1m": 4.0, "cost_score": 75,
     "ollama_available": 0, "context_window": 200000,
     "notes": "Fast & cheap. Good for high-volume, simpler tasks."},
    {"model_name": "GPT-5.5", "provider": "OpenAI", "tier": "frontier",
     "coding_score": 95, "agentic_score": 96, "reasoning_score": 96, "speed_score": 50,
     "image_gen_score": 60, "video_gen_score": 0, "multilingual_score": 90,
     "cost_input_per_1m": 5.0, "cost_output_per_1m": 30.0, "cost_score": 10,
     "ollama_available": 0, "context_window": 128000,
     "notes": "Terminal-Bench leader. Broad ecosystem and tool use."},
    {"model_name": "GPT-5.4", "provider": "OpenAI", "tier": "mid",
     "coding_score": 88, "agentic_score": 85, "reasoning_score": 88, "speed_score": 65,
     "image_gen_score": 55, "video_gen_score": 0, "multilingual_score": 88,
     "cost_input_per_1m": 2.5, "cost_output_per_1m": 15.0, "cost_score": 35,
     "ollama_available": 0, "context_window": 128000,
     "notes": "Solid mid-tier. Good general-purpose alternative to Sonnet."},
    {"model_name": "o4-mini", "provider": "OpenAI", "tier": "efficient",
     "coding_score": 78, "agentic_score": 70, "reasoning_score": 82, "speed_score": 85,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 80,
     "cost_input_per_1m": 1.1, "cost_output_per_1m": 4.4, "cost_score": 70,
     "ollama_available": 0, "context_window": 128000,
     "notes": "Efficient reasoning model. Good for chain-of-thought tasks."},
    {"model_name": "Gemini 3.1 Pro", "provider": "Google", "tier": "frontier",
     "coding_score": 92, "agentic_score": 90, "reasoning_score": 93, "speed_score": 60,
     "image_gen_score": 50, "video_gen_score": 0, "multilingual_score": 92,
     "cost_input_per_1m": 2.5, "cost_output_per_1m": 12.0, "cost_score": 40,
     "ollama_available": 0, "context_window": 2000000,
     "notes": "Best price-to-performance frontier. Massive context window."},
    {"model_name": "Gemini 3 Flash", "provider": "Google", "tier": "efficient",
     "coding_score": 75, "agentic_score": 72, "reasoning_score": 74, "speed_score": 95,
     "image_gen_score": 40, "video_gen_score": 0, "multilingual_score": 85,
     "cost_input_per_1m": 0.1, "cost_output_per_1m": 0.4, "cost_score": 95,
     "ollama_available": 0, "context_window": 1000000,
     "notes": "Extremely cheap and fast. Great for high-volume agent loops."},
    # --- Open / Ollama models ---
    {"model_name": "Qwen3-Coder 30B", "provider": "Alibaba", "tier": "mid",
     "coding_score": 88, "agentic_score": 85, "reasoning_score": 82, "speed_score": 55,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 90,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 1, "ollama_model_name": "qwen3-coder:30b",
     "context_window": 131072,
     "notes": "Best local coding model. Needs ~22GB VRAM for Q4."},
    {"model_name": "Qwen3-Coder 7B", "provider": "Alibaba", "tier": "efficient",
     "coding_score": 72, "agentic_score": 65, "reasoning_score": 68, "speed_score": 88,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 82,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 1, "ollama_model_name": "qwen3-coder:7b",
     "context_window": 131072,
     "notes": "Great for limited VRAM (<16GB). Fast local coding."},
    {"model_name": "DeepSeek V4", "provider": "DeepSeek", "tier": "mid",
     "coding_score": 86, "agentic_score": 80, "reasoning_score": 90, "speed_score": 50,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 80,
     "cost_input_per_1m": 0.14, "cost_output_per_1m": 0.28, "cost_score": 92,
     "ollama_available": 1, "ollama_model_name": "deepseek-v4",
     "context_window": 128000,
     "notes": "Aggressive pricing. Top value for high-volume ops."},
    {"model_name": "DeepSeek R1", "provider": "DeepSeek", "tier": "mid",
     "coding_score": 85, "agentic_score": 78, "reasoning_score": 92, "speed_score": 40,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 75,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 1, "ollama_model_name": "deepseek-r1",
     "context_window": 128000,
     "notes": "Best reasoning-first local model. Complex debugging champion."},
    {"model_name": "Llama 3.3 70B", "provider": "Meta", "tier": "mid",
     "coding_score": 82, "agentic_score": 80, "reasoning_score": 84, "speed_score": 35,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 85,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 1, "ollama_model_name": "llama3.3:70b",
     "context_window": 128000,
     "notes": "Premier general-purpose local model. Needs 40GB+ VRAM."},
    {"model_name": "Llama 3.3 8B", "provider": "Meta", "tier": "efficient",
     "coding_score": 62, "agentic_score": 55, "reasoning_score": 60, "speed_score": 90,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 70,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 1, "ollama_model_name": "llama3.3:8b",
     "context_window": 128000,
     "notes": "Default Ollama model. Fast, fits on most GPUs."},
    {"model_name": "Mistral Small 4", "provider": "Mistral", "tier": "efficient",
     "coding_score": 70, "agentic_score": 62, "reasoning_score": 68, "speed_score": 92,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 88,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 1, "ollama_model_name": "mistral-small",
     "context_window": 32000,
     "notes": "Best quality-to-RAM ratio. Ideal for low-latency IDE use."},
    {"model_name": "Gemma 4 26B", "provider": "Google", "tier": "mid",
     "coding_score": 74, "agentic_score": 72, "reasoning_score": 75, "speed_score": 65,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 78,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 1, "ollama_model_name": "gemma4:26b",
     "context_window": 128000,
     "notes": "Native function calling and JSON output. Great for agents."},
    # --- Newer / less familiar models ---
    {"model_name": "Amazon Nova Pro", "provider": "Amazon", "tier": "mid",
     "coding_score": 75, "agentic_score": 72, "reasoning_score": 76, "speed_score": 80,
     "image_gen_score": 35, "video_gen_score": 20, "multilingual_score": 78,
     "cost_input_per_1m": 0.8, "cost_output_per_1m": 3.2, "cost_score": 78,
     "ollama_available": 0, "context_window": 300000,
     "notes": "Enterprise-grade via Bedrock. Good price-performance."},
    {"model_name": "Amazon Nova Micro", "provider": "Amazon", "tier": "efficient",
     "coding_score": 58, "agentic_score": 50, "reasoning_score": 55, "speed_score": 97,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 65,
     "cost_input_per_1m": 0.04, "cost_output_per_1m": 0.14, "cost_score": 98,
     "ollama_available": 0, "context_window": 128000,
     "notes": "Ultra-fast, ultra-cheap. Leading TTFT latency."},
    {"model_name": "Kimi K2", "provider": "Moonshot AI", "tier": "mid",
     "coding_score": 78, "agentic_score": 74, "reasoning_score": 80, "speed_score": 68,
     "image_gen_score": 0, "video_gen_score": 0, "multilingual_score": 92,
     "cost_input_per_1m": 0.6, "cost_output_per_1m": 2.0, "cost_score": 82,
     "ollama_available": 0, "context_window": 200000,
     "notes": "Strong multilingual & research tasks. Competitive pricing."},
    # --- Image generation models ---
    {"model_name": "GPT Image 2", "provider": "OpenAI", "tier": "frontier", "category": "image",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 70,
     "image_gen_score": 95, "video_gen_score": 0, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 50,
     "ollama_available": 0, "context_window": 0,
     "notes": "Top image arena. Best text rendering and prompt adherence."},
    {"model_name": "Flux 2 Pro", "provider": "Black Forest Labs", "tier": "frontier", "category": "image",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 65,
     "image_gen_score": 93, "video_gen_score": 0, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 55,
     "ollama_available": 0, "context_window": 0,
     "notes": "Photorealism benchmark. Open-weight option available."},
    {"model_name": "Midjourney v7", "provider": "Midjourney", "tier": "frontier", "category": "image",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 60,
     "image_gen_score": 92, "video_gen_score": 0, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 45,
     "ollama_available": 0, "context_window": 0,
     "notes": "Artist's choice. Unmatched aesthetic quality and creativity."},
    {"model_name": "Stable Diffusion 3.5", "provider": "Stability AI", "tier": "mid", "category": "image",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 80,
     "image_gen_score": 78, "video_gen_score": 0, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 100,
     "ollama_available": 0, "context_window": 0,
     "notes": "Full local control. LoRA fine-tuning, total privacy."},
    # --- Video generation models ---
    {"model_name": "Google Veo 3.1", "provider": "Google", "tier": "frontier", "category": "video",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 55,
     "image_gen_score": 0, "video_gen_score": 95, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 40,
     "ollama_available": 0, "context_window": 0,
     "notes": "Best overall video. Native audio sync, cinematic realism."},
    {"model_name": "Kling 3.0", "provider": "Kuaishou", "tier": "frontier", "category": "video",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 50,
     "image_gen_score": 0, "video_gen_score": 92, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 55,
     "ollama_available": 0, "context_window": 0,
     "notes": "Long-form powerhouse. Up to 2min with character consistency."},
    {"model_name": "Sora 2", "provider": "OpenAI", "tier": "frontier", "category": "video",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 40,
     "image_gen_score": 0, "video_gen_score": 90, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 35,
     "ollama_available": 0, "context_window": 0,
     "notes": "Gold standard for photorealistic hero shots and physics."},
    {"model_name": "Runway Gen-4.5", "provider": "Runway", "tier": "mid", "category": "video",
     "coding_score": 0, "agentic_score": 0, "reasoning_score": 0, "speed_score": 60,
     "image_gen_score": 0, "video_gen_score": 88, "multilingual_score": 0,
     "cost_input_per_1m": 0.0, "cost_output_per_1m": 0.0, "cost_score": 50,
     "ollama_available": 0, "context_window": 0,
     "notes": "Filmmaker's suite. Best directorial control and editing tools."},
]


def _get_db_path(repo_path: str) -> str:
    return os.path.join(repo_path, ".exegol", DB_NAME)


def _get_conn(repo_path: str) -> sqlite3.Connection:
    db_path = _get_db_path(repo_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def seed_if_empty(repo_path: str) -> int:
    """Seeds the database with initial benchmark data if empty. Returns row count."""
    conn = _get_conn(repo_path)
    count = conn.execute("SELECT COUNT(*) FROM model_benchmarks").fetchone()[0]
    if count > 0:
        conn.close()
        return count
    now = datetime.datetime.now().isoformat()
    for m in SEED_DATA:
        m.setdefault("category", "general")
        m.setdefault("ollama_model_name", "")
        m["assessed_at"] = now
        cols = ", ".join(m.keys())
        placeholders = ", ".join(["?"] * len(m))
        conn.execute(f"INSERT OR IGNORE INTO model_benchmarks ({cols}) VALUES ({placeholders})", list(m.values()))
    conn.commit()
    final = conn.execute("SELECT COUNT(*) FROM model_benchmarks").fetchone()[0]
    conn.close()
    return final


def upsert_model(repo_path: str, data: Dict[str, Any]) -> None:
    """Insert or update a model benchmark entry."""
    conn = _get_conn(repo_path)
    data.setdefault("assessed_at", datetime.datetime.now().isoformat())
    data.setdefault("category", "general")
    data.setdefault("ollama_model_name", "")
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    updates = ", ".join([f"{k}=excluded.{k}" for k in data.keys() if k not in ("model_name", "provider")])
    sql = f"INSERT INTO model_benchmarks ({cols}) VALUES ({placeholders}) ON CONFLICT(model_name, provider) DO UPDATE SET {updates}"
    conn.execute(sql, list(data.values()))
    conn.commit()
    conn.close()


def get_all_models(repo_path: str, category: Optional[str] = None) -> List[Dict]:
    """Returns all models, optionally filtered by category."""
    seed_if_empty(repo_path)
    conn = _get_conn(repo_path)
    if category:
        rows = conn.execute("SELECT * FROM model_benchmarks WHERE category = ? ORDER BY coding_score DESC", (category,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM model_benchmarks ORDER BY coding_score DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compare_models(repo_path: str, model_names: List[str]) -> Dict[str, Any]:
    """Compare selected models side-by-side with a familiar reference."""
    seed_if_empty(repo_path)
    conn = _get_conn(repo_path)
    placeholders = ",".join(["?"] * len(model_names))
    rows = conn.execute(
        f"SELECT * FROM model_benchmarks WHERE model_name IN ({placeholders})",
        model_names
    ).fetchall()
    conn.close()

    if not rows:
        return {"error": "No matching models found", "available": [m["model_name"] for m in get_all_models(repo_path)]}

    models = [dict(r) for r in rows]
    factors = ["coding_score", "agentic_score", "reasoning_score", "speed_score",
               "image_gen_score", "video_gen_score", "cost_score", "multilingual_score"]

    comparison = {"models": models, "factor_winners": {}}
    for f in factors:
        scored = [(m["model_name"], m[f]) for m in models if m[f] > 0]
        if scored:
            winner = max(scored, key=lambda x: x[1])
            comparison["factor_winners"][f] = {"winner": winner[0], "score": winner[1]}

    return comparison


def recommend_for_role(repo_path: str, role: str) -> List[Dict]:
    """Recommend best models for a given agent role."""
    seed_if_empty(repo_path)
    role_weights = {
        "coding": {"coding_score": 0.4, "agentic_score": 0.2, "speed_score": 0.15, "cost_score": 0.15, "reasoning_score": 0.1},
        "research": {"reasoning_score": 0.3, "multilingual_score": 0.2, "speed_score": 0.2, "cost_score": 0.2, "coding_score": 0.1},
        "writing": {"reasoning_score": 0.3, "multilingual_score": 0.25, "speed_score": 0.15, "cost_score": 0.2, "coding_score": 0.1},
        "ops": {"speed_score": 0.3, "cost_score": 0.3, "agentic_score": 0.2, "coding_score": 0.1, "reasoning_score": 0.1},
        "creative": {"image_gen_score": 0.35, "video_gen_score": 0.25, "speed_score": 0.15, "cost_score": 0.25},
        "general": {"coding_score": 0.2, "agentic_score": 0.2, "reasoning_score": 0.2, "speed_score": 0.2, "cost_score": 0.2},
    }
    weights = role_weights.get(role, role_weights["general"])

    all_models = get_all_models(repo_path)
    scored = []
    for m in all_models:
        total = sum(m.get(k, 0) * w for k, w in weights.items())
        scored.append({**m, "weighted_score": round(total, 1)})

    scored.sort(key=lambda x: x["weighted_score"], reverse=True)
    return scored[:5]


def search_models(repo_path: str, query: str) -> List[Dict]:
    """Search models by name or provider."""
    seed_if_empty(repo_path)
    conn = _get_conn(repo_path)
    rows = conn.execute(
        "SELECT * FROM model_benchmarks WHERE model_name LIKE ? OR provider LIKE ? OR notes LIKE ?",
        (f"%{query}%", f"%{query}%", f"%{query}%")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ollama_models(repo_path: str) -> List[Dict]:
    """Get all models available on Ollama."""
    seed_if_empty(repo_path)
    conn = _get_conn(repo_path)
    rows = conn.execute("SELECT * FROM model_benchmarks WHERE ollama_available = 1 ORDER BY coding_score DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
