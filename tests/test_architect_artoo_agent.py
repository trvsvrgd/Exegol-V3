import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agents.architect_artoo_agent import ArchitectArtooAgent


class StaticClient:
    def generate_system_prompt(self, _agent):
        return "system"


def test_architect_artoo_normalizes_dict_findings_to_tasks():
    agent = ArchitectArtooAgent(StaticClient())

    task = agent._architecture_task_from_finding({
        "title": "Crash recovery gap",
        "recommendation": "Dispatch auto-failure backlog items before normal work.",
        "severity": "critical",
    })

    assert task["id"].startswith("arch_fix_crash_recovery_gap_")
    assert task["summary"] == "Architectural Issue: Crash recovery gap"
    assert task["priority"] == "critical"
    assert task["rationale"] == "Dispatch auto-failure backlog items before normal work."
