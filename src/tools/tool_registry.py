import os
import json
from typing import List, Dict, Any

class ToolRegistry:
    """Central registry for all tools available to Exegol agents.
    
    Stores descriptions, risk levels, and other metadata.
    """
    
    TOOLS = {
        "file_editor": {
            "description": "Edits existing files in the repository with safety checks.",
            "risk": "high",
            "category": "filesystem"
        },
        "slack_notifier": {
            "description": "Sends notifications and progress updates to Slack channels.",
            "risk": "low",
            "category": "communication"
        },
        "agentic_coding": {
            "description": "Generates and implements complex code changes across multiple files.",
            "risk": "critical",
            "category": "core"
        },
        "sandbox_orchestrator": {
            "description": "Runs code in an isolated environment to validate behavior.",
            "risk": "medium",
            "category": "testing"
        },
        "web_search": {
            "description": "Performs web searches to gather external technical context.",
            "risk": "low",
            "category": "research"
        },
        "backlog_grooming": {
            "description": "Analyzes and prioritizes repository tasks in backlog.json.",
            "risk": "medium",
            "category": "management"
        },
        "prompt_generation": {
            "description": "Creates optimized LLM prompts for other agents.",
            "risk": "low",
            "category": "core"
        },
        "user_prompting": {
            "description": "Interactive tool for user clarification and project onboarding via Slack/Workbench.",
            "risk": "low",
            "category": "communication"
        },
        "clarification_engine": {
            "description": "AI-driven engine for generating onboarding questions and analyzing roadmap impact.",
            "risk": "low",
            "category": "strategic"
        },
        "thrawn_intel_manager": {
            "description": "Manages project intent and strategic documentation.",
            "risk": "medium",
            "category": "strategic"
        },
        "gmail_api": {
            "description": "Interfaces with Gmail for reporting and alerts.",
            "risk": "medium",
            "category": "communication"
        },
        "drive_sync": {
            "description": "Synchronizes artifacts and reports to Google Drive.",
            "risk": "medium",
            "category": "filesystem"
        },
        "cost_analyzer": {
            "description": "Calculates and reports LLM and infrastructure costs.",
            "risk": "low",
            "category": "finops"
        },
        "markdown_formatter": {
            "description": "Ensures all markdown files meet repository standards.",
            "risk": "low",
            "category": "formatting"
        },
        "file_namer": {
            "description": "Suggests standardized names for new files.",
            "risk": "low",
            "category": "formatting"
        },
        "diagram_generator": {
            "description": "Generates Mermaid or DOT diagrams for architecture.",
            "risk": "low",
            "category": "documentation"
        },
        "readme_parser": {
            "description": "Analyzes root README for architectural constraints.",
            "risk": "low",
            "category": "documentation"
        },
        "architecture_reviewer": {
            "description": "Audits proposed changes against project architecture.",
            "risk": "high",
            "category": "strategic"
        },
        "schema_designer": {
            "description": "Generates and validates database or JSON schemas.",
            "risk": "medium",
            "category": "core"
        },
        "docker_compose_generator": {
            "description": "Creates and modifies Docker Compose configurations.",
            "risk": "medium",
            "category": "infrastructure"
        },
        "git_monitoring": {
            "description": "Tracks repository changes and identifies drift.",
            "risk": "low",
            "category": "infrastructure"
        },
        "interaction_log_reader": {
            "description": "Analyzes agent interaction logs for patterns and errors.",
            "risk": "low",
            "category": "telemetry"
        },
        "model_comparison": {
            "description": "Evaluates LLM models and backends for performance and financial Total Cost of Ownership (TCO).",
            "risk": "low",
            "category": "strategic"
        },
        "backlog_writer": {
            "description": "Adds new tasks to the repository backlog.",
            "risk": "medium",
            "category": "management"
        },
        "arxiv_reader": {
            "description": "Fetches and summarizes recent AI research papers.",
            "risk": "low",
            "category": "research"
        },
        "agent_introspection": {
            "description": "Allows an agent to analyze its own performance metrics.",
            "risk": "low",
            "category": "telemetry"
        },
        "repo_analyzer": {
            "description": "Deep scans repository for code quality and patterns.",
            "risk": "medium",
            "category": "telemetry"
        },
        "todo_reporter": {
            "description": "Collects and reports all TODO/FIXME comments.",
            "risk": "low",
            "category": "telemetry"
        },
        "test_runner": {
            "description": "Executes unit and integration tests.",
            "risk": "medium",
            "category": "testing"
        },
        "linter": {
            "description": "Runs static analysis and linting tools.",
            "risk": "low",
            "category": "testing"
        },
        "uat_sandbox": {
            "description": "Launches User Acceptance Testing environments.",
            "risk": "high",
            "category": "testing"
        },
        "sandbox_validator": {
            "description": "Verifies state of sandbox after test execution.",
            "risk": "low",
            "category": "testing"
        },
        "capability_reviewer": {
            "description": "Maps system features to regulatory requirements (EU AI Act, NIST AI RMF) automatically via ID, keyword, and semantic matching. Produces gap analysis reports for ComplianceCodyAgent.",
            "risk": "low",
            "category": "compliance"
        },
        "repo_scanner": {
            "description": "Scans repository for security vulnerabilities.",
            "risk": "medium",
            "category": "security"
        },
        "risk_scorer": {
            "description": "Calculates risk scores for proposed architectural changes.",
            "risk": "low",
            "category": "security"
        },
        "app_scaffolding": {
            "description": "Generates initial project structure and boilerplate based on schema.",
            "risk": "medium",
            "category": "core"
        },
        "secret_manager": {
            "description": "Manages API key lifecycle: health checks, rotation, age tracking, and HITL escalation.",
            "risk": "high",
            "category": "security"
        }
    }


    @classmethod
    def get_all_tools(cls) -> Dict[str, Any]:
        return cls.TOOLS

    @classmethod
    def get_tool(cls, tool_id: str) -> Dict[str, Any]:
        return cls.TOOLS.get(tool_id, {
            "description": "Unknown tool.",
            "risk": "unknown",
            "category": "unknown"
        })
