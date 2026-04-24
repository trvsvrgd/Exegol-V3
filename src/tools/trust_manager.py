import os
import json
from datetime import datetime
from typing import Dict, Any, List

class TrustManager:
    """Manages agent reputation (trust) scores and enforces autonomy thresholds."""

    _config_cache: Dict[str, Any] = {}
    _config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "agent_trust.json")

    @classmethod
    def _load_config(cls):
        if os.path.exists(cls._config_path):
            with open(cls._config_path, "r", encoding="utf-8") as f:
                cls._config_cache = json.load(f)
        return cls._config_cache

    @classmethod
    def _save_config(cls):
        with open(cls._config_path, "w", encoding="utf-8") as f:
            json.dump(cls._config_cache, f, indent=2)

    @classmethod
    def get_score(cls, agent_id: str) -> int:
        config = cls._load_config()
        agent_data = config.get("agents", {}).get(agent_id, config.get("agents", {}).get("default", {"score": 70}))
        return agent_data.get("score", 70)

    @classmethod
    def update_score(cls, agent_id: str, change: int, reason: str):
        """Updates an agent's trust score and records the event in history."""
        config = cls._load_config()
        if agent_id not in config["agents"]:
            config["agents"][agent_id] = config["agents"].get("default", {"score": 70, "history": []}).copy()
            config["agents"][agent_id]["history"] = []

        agent_data = config["agents"][agent_id]
        old_score = agent_data["score"]
        
        # Apply mechanics
        new_score = old_score + change
        new_score = max(config["mechanics"]["min_score"], min(config["mechanics"]["max_score"], new_score))
        
        agent_data["score"] = new_score
        agent_data["last_updated"] = datetime.now().isoformat()
        agent_data["history"].append({
            "timestamp": datetime.now().isoformat(),
            "change": change,
            "new_score": new_score,
            "reason": reason
        })
        
        # Keep history manageable (last 20 events)
        if len(agent_data["history"]) > 20:
            agent_data["history"] = agent_data["history"][-20:]
            
        cls._save_config()
        print(f"[TrustManager] Agent '{agent_id}' score: {old_score} -> {new_score} ({reason})")

    @classmethod
    def check_autonomy(cls, agent_id: str) -> str:
        """Determines the autonomy level for an agent based on trust score."""
        score = cls.get_score(agent_id)
        config = cls._load_config()
        thresholds = config.get("thresholds", {})
        
        if score <= thresholds.get("suspension", 20):
            return "SUSPENDED"
        if score <= thresholds.get("force_hitl", 50):
            return "FORCE_HITL"
        if score >= thresholds.get("full_autonomy", 80):
            return "FULL_AUTONOMY"
        return "STANDARD"
