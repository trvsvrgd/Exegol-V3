import os
import json
from typing import List, Dict, Any

class RBACManager:
    """Manages agent roles and enforces permission boundaries."""

    _config_cache: Dict[str, Any] = {}
    _config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "agent_rbac.json")

    @classmethod
    def _load_config(cls):
        if not cls._config_cache:
            if os.path.exists(cls._config_path):
                with open(cls._config_path, "r", encoding="utf-8") as f:
                    cls._config_cache = json.load(f)
            else:
                print(f"[RBACManager] Warning: Config not found at {cls._config_path}")
                cls._config_cache = {"roles": {}, "agent_roles": {}, "global_restrictions": {}}
        return cls._config_cache

    @classmethod
    def check_permission(cls, agent_id: str, permission: str, target_path: Optional[str] = None) -> bool:
        """Checks if an agent has a specific permission, optionally for a specific path."""
        config = cls._load_config()
        
        # 1. Get agent role
        role_name = config.get("agent_roles", {}).get(agent_id)
        if not role_name:
            print(f"[RBACManager] Warning: Agent '{agent_id}' has no assigned role. Defaulting to 'restricted'.")
            role_name = "restricted"

        # 2. Get role permissions
        role_data = config.get("roles", {}).get(role_name, {})
        permissions = role_data.get("permissions", [])

        # 3. Check for specific permission
        if permission in permissions:
            return True
            
        # 4. Check for path-specific grants (if permission is denied at role level)
        if permission == "filesystem:write" and target_path:
            grants = config.get("path_grants", {}).get(agent_id, [])
            # Normalize target_path to be relative to workspace root if possible, or just check suffix
            for grant in grants:
                if target_path.endswith(grant.replace("/", os.sep)):
                    print(f"[RBACManager] Path grant matched: {agent_id} -> {grant}")
                    return True

        # 5. Check global restrictions (overrides)
        restriction = config.get("global_restrictions", {}).get(permission)
        if restriction == "requires_hitl":
            # This logic should be handled by the caller to trigger HITL if needed
            # For this check, we return False to indicate it's not a 'granted' permission
            return False

        return False

    @classmethod
    def get_agent_permissions(cls, agent_id: str) -> List[str]:
        config = cls._load_config()
        role_name = config.get("agent_roles", {}).get(agent_id, "restricted")
        return config.get("roles", {}).get(role_name, {}).get("permissions", [])
