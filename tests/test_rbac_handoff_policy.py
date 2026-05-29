import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tools.rbac_manager import RBACManager


def test_autonomous_handoff_callers_have_trigger_permission():
    RBACManager._config_cache = {}

    handoff_callers = [
        "developer_dex",
        "product_poe",
        "quality_quigon",
        "architect_artoo",
        "thoughtful_thrawn",
        "intel_ima",
        "research_rex",
        "security_sabine",
        "uat_ulic",
        "watcher_wedge",
    ]

    for agent_id in handoff_callers:
        assert RBACManager.check_permission(agent_id, "agent:trigger"), agent_id


def test_restricted_agents_do_not_gain_trigger_permission():
    RBACManager._config_cache = {}

    assert not RBACManager.check_permission("vibe_vader", "agent:trigger")
    assert not RBACManager.check_permission("unknown_agent", "agent:trigger")
