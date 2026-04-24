import os
import json
from urllib.parse import urlparse
from typing import Any, Dict

class EgressFilter:
    """Filters outbound network requests based on an allowlist of domains."""

    _config_cache: Dict[str, Any] = {}
    _config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "egress_allowlist.json")

    @classmethod
    def _load_config(cls):
        if not cls._config_cache:
            if os.path.exists(cls._config_path):
                with open(cls._config_path, "r", encoding="utf-8") as f:
                    cls._config_cache = json.load(f)
            else:
                print(f"[EgressFilter] Warning: Config not found at {cls._config_path}")
                cls._config_cache = {"allowed_domains": [], "enforce_egress": False}
        return cls._config_cache

    @classmethod
    def is_url_allowed(cls, url: str) -> bool:
        """Checks if the given URL is allowed by the egress policy."""
        config = cls._load_config()
        if not config.get("enforce_egress", False):
            return True

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.split(":")[0]  # Remove port if present
            
            if not domain:
                # Relative URL or malformed?
                return False
                
            allowed_domains = config.get("allowed_domains", [])
            
            # Check for exact match or subdomain match
            for allowed in allowed_domains:
                if domain == allowed or domain.endswith("." + allowed):
                    return True
                    
            return False
        except Exception as e:
            print(f"[EgressFilter] Error parsing URL {url}: {e}")
            return False

    @classmethod
    def validate_request(cls, url: str):
        """Raises a PermissionError if the URL is not allowed."""
        if not cls.is_url_allowed(url):
            from tools.security_audit_logger import log_security_event
            log_security_event(
                actor="egress_filter",
                action="egress_blocked",
                outcome="blocked",
                details={"attempted_url": url}
            )
            raise PermissionError(f"Egress Blocked: Destination '{url}' is not in the allowlist.")
