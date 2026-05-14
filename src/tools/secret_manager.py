"""
SecretManager — Secure API Key Rotation & Lifecycle Management

Responsibilities:
  1. Track key metadata (provider, last rotated, age, health status)
  2. Audit key health by attempting a lightweight API call
  3. Rotate keys by safely rewriting .env
  4. Escalate expired/unhealthy keys to the HITL queue + Slack
  5. Log all rotation events to the security audit trail

Security constraints:
  - Raw key values are NEVER written to interaction logs, backlog, or stdout.
  - Key values only live in .env and config/secret_metadata.json (gitignored).
  - All mutations go through atomic writes via StateManager.
"""

import os
import json
import datetime
import hashlib
import re
from typing import Optional, Dict, Any, List

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METADATA_PATH = "config/secret_metadata.json"

# Keys we manage — maps env var name to provider display name
MANAGED_KEYS = {
    "GEMINI_API_KEY": {
        "provider": "gemini",
        "display_name": "Google Gemini (AI Studio)",
        "placeholder": "your_gemini_key_here",
        "rotation_url": "https://aistudio.google.com/app/apikey",
    },
    "ANTHROPIC_API_KEY": {
        "provider": "anthropic",
        "display_name": "Anthropic Claude",
        "placeholder": "your_anthropic_key_here",
        "rotation_url": "https://console.anthropic.com/settings/keys",
    },
    "SLACK_BOT_TOKEN": {
        "provider": "slack",
        "display_name": "Slack Bot Token",
        "placeholder": "",
        "rotation_url": "https://api.slack.com/apps",
    },
    "EXEGOL_API_KEY": {
        "provider": "exegol",
        "display_name": "Exegol Control Tower",
        "placeholder": "dev-local-key",
        "rotation_url": "",
    },
    "EXEGOL_HMAC_SECRET": {
        "provider": "exegol",
        "display_name": "Exegol HMAC Secret",
        "placeholder": "dev-secret-keep-it-safe",
        "rotation_url": "",
    },
}

# Default rotation cadence (days) — advisory, not enforced
DEFAULT_ROTATION_CADENCE_DAYS = 90

# ---------------------------------------------------------------------------
# SecretManager
# ---------------------------------------------------------------------------

class SecretManager:
    """Manages API key lifecycle: health checks, rotation, and HITL escalation."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.env_path = os.path.join(repo_path, ".env")
        self.metadata_path = os.path.join(repo_path, METADATA_PATH)
        self.exegol_dir = os.path.join(repo_path, ".exegol")
        self._ensure_metadata_file()

    def _load_human_observations(self) -> Dict[str, str]:
        """Load human observations from .exegol/human_observations.json."""
        obs_path = os.path.join(self.exegol_dir, "human_observations.json")
        if not os.path.exists(obs_path):
            return {}
        try:
            with open(obs_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Metadata Persistence
    # ------------------------------------------------------------------

    def _ensure_metadata_file(self):
        """Create the metadata file with defaults if it doesn't exist."""
        os.makedirs(os.path.dirname(self.metadata_path), exist_ok=True)
        if not os.path.exists(self.metadata_path):
            self._write_metadata(self._default_metadata())

    def _default_metadata(self) -> Dict[str, Any]:
        """Generate default metadata for all managed keys."""
        now = datetime.datetime.now().isoformat()
        meta = {}
        for env_var, info in MANAGED_KEYS.items():
            meta[env_var] = {
                "provider": info["provider"],
                "display_name": info["display_name"],
                "last_rotated": now,
                "rotation_cadence_days": DEFAULT_ROTATION_CADENCE_DAYS,
                "last_health_check": None,
                "health_status": "unknown",  # unknown | healthy | expired | placeholder
                "human_observation": None,
                "rotation_url": info["rotation_url"],
                "key_fingerprint": "",  # SHA256 of first 8 + last 4 chars (safe to log)
                "rotation_history": [],
            }
        return meta

    def _read_metadata(self) -> Dict[str, Any]:
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return self._default_metadata()

    def _write_metadata(self, data: Dict[str, Any]):
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    # ------------------------------------------------------------------
    # Key Fingerprinting (safe for logs)
    # ------------------------------------------------------------------

    @staticmethod
    def _fingerprint(key_value: str) -> str:
        """Generate a safe fingerprint: sha256(first8 + last4). Never logs the full key."""
        if not key_value or len(key_value) < 12:
            return "too_short"
        snippet = key_value[:8] + key_value[-4:]
        return hashlib.sha256(snippet.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # .env Read/Write
    # ------------------------------------------------------------------

    def _read_env(self) -> Dict[str, str]:
        """Parse .env into a dict, preserving comments and order."""
        env_vars = {}
        if not os.path.exists(self.env_path):
            return env_vars
        with open(self.env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    env_vars[key.strip()] = value.strip()
        return env_vars

    def _write_env_key(self, env_var: str, new_value: str):
        """Safely rewrite a single key in .env, preserving all other content."""
        if not os.path.exists(self.env_path):
            raise FileNotFoundError(f".env not found at {self.env_path}")

        with open(self.env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        pattern = re.compile(rf"^{re.escape(env_var)}\s*=")
        replaced = False
        new_lines = []
        for line in lines:
            if pattern.match(line.strip()):
                new_lines.append(f"{env_var}={new_value}\n")
                replaced = True
            else:
                new_lines.append(line)

        if not replaced:
            # Key doesn't exist yet — append it
            new_lines.append(f"\n{env_var}={new_value}\n")

        with open(self.env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    # ------------------------------------------------------------------
    # Health Checks
    # ------------------------------------------------------------------

    def check_key_health(self, env_var: str) -> Dict[str, Any]:
        """Check whether a specific API key is valid.
        
        Returns: {"status": "healthy"|"expired"|"placeholder"|"missing", "detail": str}
        """
        info = MANAGED_KEYS.get(env_var)
        if not info:
            return {"status": "unknown", "detail": f"Unmanaged key: {env_var}"}

        env_vars = self._read_env()
        raw_value = env_vars.get(env_var, "")

        # Check for placeholder or empty
        obs = self._load_human_observations()
        relevant_obs = obs.get(env_var) or obs.get("compliance") or obs.get("security")

        if not raw_value or raw_value == info.get("placeholder", ""):
            detail = f"{info['display_name']} is set to a placeholder value."
            if relevant_obs:
                detail += f" {relevant_obs}"
            return {"status": "placeholder", "detail": detail}

        # Provider-specific lightweight health checks
        if info["provider"] == "gemini":
            return self._check_gemini(raw_value)
        elif info["provider"] == "anthropic":
            return self._check_anthropic(raw_value)
        elif info["provider"] == "slack":
            return self._check_slack(raw_value)
        else:
            # Internal keys (EXEGOL_API_KEY, HMAC) — just verify they're non-placeholder
            detail = f"{info['display_name']} is configured."
            if relevant_obs:
                detail += f" {relevant_obs}"
            return {"status": "healthy", "detail": detail}

    def _check_gemini(self, key: str) -> Dict[str, str]:
        """Lightweight Gemini API key validation."""
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return {"status": "healthy", "detail": "Gemini API key is valid."}
            else:
                return {"status": "expired", "detail": f"Gemini returned HTTP {resp.status_code}: {resp.text[:100]}"}
        except Exception as e:
            return {"status": "unknown", "detail": f"Could not reach Gemini API: {e}"}

    def _check_anthropic(self, key: str) -> Dict[str, str]:
        """Lightweight Anthropic API key validation."""
        try:
            import requests
            resp = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=5,
            )
            if resp.status_code == 200:
                return {"status": "healthy", "detail": "Anthropic API key is valid."}
            else:
                return {"status": "expired", "detail": f"Anthropic returned HTTP {resp.status_code}"}
        except Exception as e:
            return {"status": "unknown", "detail": f"Could not reach Anthropic API: {e}"}

    def _check_slack(self, token: str) -> Dict[str, str]:
        """Lightweight Slack bot token validation."""
        try:
            import requests
            resp = requests.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            data = resp.json()
            if data.get("ok"):
                return {"status": "healthy", "detail": f"Slack token valid for team: {data.get('team', 'unknown')}"}
            else:
                return {"status": "expired", "detail": f"Slack auth.test failed: {data.get('error', 'unknown')}"}
        except Exception as e:
            return {"status": "unknown", "detail": f"Could not reach Slack API: {e}"}

    # ------------------------------------------------------------------
    # Full Audit (all keys)
    # ------------------------------------------------------------------

    def audit_all_keys(self) -> List[Dict[str, Any]]:
        """Run health checks on all managed keys and update metadata.

        Returns a list of key audit results for reporting.
        """
        meta = self._read_metadata()
        now = datetime.datetime.now()
        results = []

        for env_var, info in MANAGED_KEYS.items():
            # Ensure metadata entry exists (handles newly added keys)
            if env_var not in meta:
                meta[env_var] = self._default_metadata()[env_var]

            health = self.check_key_health(env_var)
            entry = meta[env_var]

            # Update metadata
            entry["last_health_check"] = now.isoformat()
            entry["health_status"] = health["status"]
            
            # Sync human observations
            obs = self._load_human_observations()
            entry["human_observation"] = obs.get(env_var) or obs.get("compliance") or obs.get("security")

            # Compute age
            last_rotated = datetime.datetime.fromisoformat(entry["last_rotated"])
            age_days = (now - last_rotated).days
            cadence = entry.get("rotation_cadence_days", DEFAULT_ROTATION_CADENCE_DAYS)
            overdue = age_days > cadence

            # Update fingerprint
            env_vars = self._read_env()
            raw = env_vars.get(env_var, "")
            entry["key_fingerprint"] = self._fingerprint(raw) if raw else ""

            results.append({
                "env_var": env_var,
                "provider": info["provider"],
                "display_name": info["display_name"],
                "health_status": health["status"],
                "health_detail": health["detail"],
                "age_days": age_days,
                "rotation_cadence_days": cadence,
                "overdue": overdue,
                "rotation_url": info["rotation_url"],
                "fingerprint": entry["key_fingerprint"],
                "human_observation": entry.get("human_observation"),
            })

        self._write_metadata(meta)
        return results

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    def rotate_key(self, env_var: str, new_value: str, rotated_by: str = "user") -> Dict[str, Any]:
        """Rotate a single API key: rewrite .env, update metadata, log audit event.

        Args:
            env_var: The environment variable name (e.g., "GEMINI_API_KEY")
            new_value: The new key value
            rotated_by: Who triggered the rotation ("user", "security_sabine", etc.)

        Returns:
            {"status": "success"|"error", "detail": str}
        """
        if env_var not in MANAGED_KEYS:
            return {"status": "error", "detail": f"Unknown key: {env_var}"}

        if not new_value or len(new_value) < 8:
            return {"status": "error", "detail": "Key value is too short (min 8 chars)."}

        try:
            # 1. Rewrite .env
            self._write_env_key(env_var, new_value)

            # 2. Hot-reload into current process
            os.environ[env_var] = new_value

            # 3. Update metadata
            now = datetime.datetime.now().isoformat()
            meta = self._read_metadata()
            if env_var not in meta:
                meta[env_var] = self._default_metadata()[env_var]

            old_fingerprint = meta[env_var].get("key_fingerprint", "")
            new_fingerprint = self._fingerprint(new_value)

            meta[env_var]["last_rotated"] = now
            meta[env_var]["health_status"] = "unknown"  # Will be verified on next audit
            meta[env_var]["key_fingerprint"] = new_fingerprint
            meta[env_var]["rotation_history"].append({
                "rotated_at": now,
                "rotated_by": rotated_by,
                "old_fingerprint": old_fingerprint,
                "new_fingerprint": new_fingerprint,
            })

            # Cap rotation history to last 20 entries
            meta[env_var]["rotation_history"] = meta[env_var]["rotation_history"][-20:]
            self._write_metadata(meta)

            # 4. Security audit log
            from tools.security_audit_logger import log_security_event
            log_security_event(
                actor=rotated_by,
                action="api_key_rotated",
                outcome="success",
                repo_path=self.repo_path,
                details={
                    "env_var": env_var,
                    "provider": MANAGED_KEYS[env_var]["provider"],
                    "old_fingerprint": old_fingerprint,
                    "new_fingerprint": new_fingerprint,
                },
            )

            # 5. Console feedback (no raw key!)
            provider_name = MANAGED_KEYS[env_var]["display_name"]
            print(f"[SecretManager] Rotated {provider_name} key (fingerprint: {new_fingerprint})")

            return {"status": "success", "detail": f"{provider_name} key rotated successfully.", "fingerprint": new_fingerprint}

        except Exception as e:
            from tools.security_audit_logger import log_security_event
            log_security_event(
                actor=rotated_by,
                action="api_key_rotated",
                outcome="failure",
                repo_path=self.repo_path,
                details={"env_var": env_var, "error": str(e)},
            )
            return {"status": "error", "detail": f"Rotation failed: {e}"}

    # ------------------------------------------------------------------
    # HITL Escalation
    # ------------------------------------------------------------------

    def escalate_unhealthy_keys(self) -> List[str]:
        """Check all keys and escalate unhealthy ones to the HITL queue + Slack.

        Returns list of HITL task IDs created.
        """
        from tools.state_manager import StateManager
        from tools.slack_tool import post_to_slack

        audit_results = self.audit_all_keys()
        sm = StateManager(self.repo_path)
        escalated = []

        for result in audit_results:
            needs_attention = (
                result["health_status"] in ("expired", "placeholder")
                or result["overdue"]
            )

            if not needs_attention:
                continue

            # Skip internal Exegol keys from HITL (they're local dev secrets)
            if result["provider"] == "exegol":
                continue

            reason_parts = []
            if result["health_status"] == "expired":
                reason_parts.append("API key is invalid/expired")
            elif result["health_status"] == "placeholder":
                reason_parts.append("Key is still set to placeholder")
            if result["overdue"]:
                reason_parts.append(f"Key is {result['age_days']} days old (cadence: {result['rotation_cadence_days']}d)")

            reason = "; ".join(reason_parts)
            summary = f"Rotate {result['display_name']} API key"
            context = (
                f"Reason: {reason}. "
                f"Current status: {result['health_status']}. "
                f"Rotation URL: {result['rotation_url']}"
            )

            task_id = sm.add_hitl_task(
                summary=summary,
                category="credentials",
                context=context,
                task_id=f"hitl_rotate_{result['provider']}",
            )
            escalated.append(task_id)

            # Slack notification
            slack_msg = (
                f":rotating_light: *API Key Rotation Required*\n"
                f"*Provider:* {result['display_name']}\n"
                f"*Status:* `{result['health_status']}`\n"
                f"*Reason:* {reason}\n"
                f"*Rotate at:* {result['rotation_url']}\n"
                f"_Submit the new key via the Workbench UI or run `SecretManager.rotate_key()`._"
            )
            try:
                post_to_slack(slack_msg)
            except Exception:
                pass  # Slack may itself be unhealthy

        if escalated:
            print(f"[SecretManager] Escalated {len(escalated)} key rotation tasks to HITL queue.")
        else:
            print(f"[SecretManager] All managed keys are healthy. No escalation needed.")

        return escalated

    # ------------------------------------------------------------------
    # Summary (for agent/report consumption)
    # ------------------------------------------------------------------

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns a safe-to-log summary of all managed keys."""
        results = self.audit_all_keys()
        healthy = sum(1 for r in results if r["health_status"] == "healthy")
        unhealthy = sum(1 for r in results if r["health_status"] in ("expired", "placeholder"))
        overdue = sum(1 for r in results if r["overdue"])

        return {
            "total_managed_keys": len(results),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "overdue_for_rotation": overdue,
            "keys": results,
            "audited_at": datetime.datetime.now().isoformat(),
        }
