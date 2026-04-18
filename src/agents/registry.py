AGENT_REGISTRY = {
    "cameraman_chimera": {
        "class": "CameramanChimeraAgent",
        "module": "agents.cameraman_chimera_agent",
        "wake_word": "record",
        "tools": ["playwright_recorder", "video_clipper"],
        "max_steps": 10
    },
    "insightful_intel": {
        "class": "InsightfulIntelAgent",
        "module": "agents.insightful_intel_agent",
        "wake_word": "report",
        "tools": ["gmail_api", "drive_sync", "cost_analyzer"],
        "max_steps": 5
    },
    "markdown_mark": {
        "class": "MarkdownMarkAgent",
        "module": "agents.markdown_mark_agent",
        "wake_word": "mark",
        "tools": ["markdown_formatter", "file_namer"],
        "max_steps": 5
    },
    "thoughtful_thunderbird": {
        "class": "ThoughtfulThunderbirdAgent",
        "module": "agents.thoughtful_thunderbird_agent",
        "wake_word": "thunderbird",
        "tools": ["user_prompting", "clarification_engine"],
        "max_steps": 5
    },
    "product_puck": {
        "class": "ProductPuckAgent",
        "module": "agents.product_puck_agent",
        "wake_word": "puck",
        "tools": ["backlog_grooming", "prompt_generation"],
        "max_steps": 10
    },
    "developer_dragon": {
        "class": "DeveloperDragonAgent",
        "module": "agents.developer_dragon_agent",
        "wake_word": "dragon",
        "tools": ["file_editor", "slack_notifier", "agentic_coding"],
        "max_steps": 20
    },
    "quality_qop": {
        "class": "QualityQopAgent",
        "module": "agents.quality_qop_agent",
        "wake_word": "qop",
        "tools": ["test_runner", "linter", "uat_sandbox"],
        "max_steps": 15
    },
    "research_raven": {
        "class": "ResourcefulRavenAgent",
        "module": "agents.research_raven_agent",
        "wake_word": "research",
        "tools": ["model_comparison", "web_search", "backlog_writer"],
        "max_steps": 10
    },
    "architect_anubis": {
        "class": "ArchitectAnubisAgent",
        "module": "agents.architect_anubis_agent",
        "wake_word": "architect",
        "tools": ["diagram_generator", "readme_parser", "architecture_reviewer"],
        "max_steps": 10
    },
    "agent_optimizer_abaddon": {
        "class": "AbaddonAgentOptimizerAgent",
        "module": "agents.agent_optimizer_abaddon_agent",
        "wake_word": "optimize",
        "tools": ["gmail_api", "interaction_log_reader", "web_search"],
        "max_steps": 10
    },
    "evaluator_enigma": {
        "class": "EvaluatorEnigmaAgent",
        "module": "agents.evaluator_enigma_agent",
        "wake_word": "evaluate",
        "tools": ["web_search", "arxiv_reader", "backlog_writer"],
        "max_steps": 15
    },
    "report_razor": {
        "class": "ReportRazorAgent",
        "module": "agents.report_razor_agent",
        "wake_word": "summary",
        "tools": ["gmail_api", "interaction_log_reader"],
        "max_steps": 10
    },
    "chief_of_staff_chen": {
        "class": "ChiefOfStaffChenAgent",
        "module": "agents.chief_of_staff_chen_agent",
        "wake_word": "review",
        "tools": ["gmail_api", "interaction_log_reader", "agent_introspection"],
        "max_steps": 15
    }
}
