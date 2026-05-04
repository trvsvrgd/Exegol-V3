AGENT_REGISTRY = {
#    "cameraman_cassian": {
#        "class": "CameramanCassianAgent",
#        "module": "agents.cameraman_cassian_agent",
#        "wake_word": "cassian",
#        "tools": ["playwright_recorder", "video_clipper"],
#        "max_steps": 10
#    },
    "intel_ima": {
        "class": "IntelImaAgent",
        "module": "agents.intel_ima_agent",
        "wake_word": "ima",
        "tools": ["gmail_api", "drive_sync", "cost_analyzer", "web_search"],
        "max_steps": 5
    },
    "markdown_mace": {
        "class": "MarkdownMaceAgent",
        "module": "agents.markdown_mace_agent",
        "wake_word": "mace",
        "tools": ["markdown_formatter", "file_namer"],
        "max_steps": 5
    },
    "thoughtful_thrawn": {
        "class": "ThoughtfulThrawnAgent",
        "module": "agents.thoughtful_thrawn_agent",
        "wake_word": "thrawn",
        "tools": ["user_prompting", "clarification_engine", "web_search"],
        "max_steps": 5
    },
    "product_poe": {
        "class": "ProductPoeAgent",
        "module": "agents.product_poe_agent",
        "wake_word": "poe",
        "tools": ["backlog_grooming", "prompt_generation", "web_search"],
        "max_steps": 10
    },
    "developer_dex": {
        "class": "DeveloperDexAgent",
        "module": "agents.developer_dex_agent",
        "wake_word": "dex",
        "tools": ["file_editor", "slack_notifier", "agentic_coding", "sandbox_orchestrator", "web_search"],
        "max_steps": 20
    },
    "research_rex": {
        "class": "ResearchRexAgent",
        "module": "agents.research_rex_agent",
        "wake_word": "rex",
        "tools": ["model_comparison", "web_search", "backlog_writer"],
        "max_steps": 10
    },
    "architect_artoo": {
        "class": "ArchitectArtooAgent",
        "module": "agents.architect_artoo_agent",
        "wake_word": "artoo",
        "tools": ["diagram_generator", "readme_parser", "architecture_reviewer", "schema_designer", "docker_compose_generator", "git_monitoring", "web_search"],
        "max_steps": 10
    },
    "optimizer_ahsoka": {
        "class": "OptimizerAhsokaAgent",
        "module": "agents.optimizer_ahsoka_agent",
        "wake_word": "ahsoka",
        "tools": ["gmail_api", "interaction_log_reader", "web_search"],
        "max_steps": 10
    },
    "evaluator_ezra": {
        "class": "EvaluatorEzraAgent",
        "module": "agents.evaluator_ezra_agent",
        "wake_word": "ezra",
        "tools": ["web_search", "arxiv_reader", "backlog_writer"],
        "max_steps": 15
    },
    "report_revan": {
        "class": "ReportRevanAgent",
        "module": "agents.report_revan_agent",
        "wake_word": "revan",
        "tools": ["gmail_api", "interaction_log_reader"],
        "max_steps": 10
    },
    "chief_of_staff_chewie": {
        "class": "ChiefOfStaffChewieAgent",
        "module": "agents.chief_of_staff_chewie_agent",
        "wake_word": "chewie",
        "tools": ["gmail_api", "interaction_log_reader", "agent_introspection"],
        "max_steps": 15
    },
    "vibe_vader": {
        "class": "VibeVaderAgent",
        "module": "agents.vibe_vader_agent",
        "wake_word": "vader",
        "tools": ["repo_analyzer", "todo_reporter", "web_search"],
        "max_steps": 10
    },
    "quality_quigon": {
        "class": "QualityQuigonAgent",
        "module": "agents.quality_quigon_agent",
        "wake_word": "quigon",
        "tools": ["test_runner", "linter", "uat_sandbox", "sandbox_validator", "web_search"],
        "max_steps": 15
    },
    "compliance_cody": {
        "class": "ComplianceCodyAgent",
        "module": "agents.compliance_cody_agent",
        "wake_word": "cody",
        "tools": ["web_search", "backlog_writer", "capability_reviewer"],
        "max_steps": 15
    },
    "security_architect": {
        "class": "SecurityArchitectAgent",
        "module": "agents.security_architect_agent",
        "wake_word": "secure",
        "tools": ["repo_scanner", "web_search", "backlog_writer", "architecture_reviewer"],
        "max_steps": 20
    },
    "assessment_anakin": {
        "class": "AssessmentAnakinAgent",
        "module": "agents.assessment_anakin_agent",
        "wake_word": "anakin",
        "tools": ["repo_analyzer", "risk_scorer", "backlog_writer", "web_search"],
        "max_steps": 15
    },
    "technical_tarkin": {
        "class": "TechnicalTarkinAgent",
        "module": "agents.technical_tarkin_agent",
        "wake_word": "tarkin",
        "tools": ["file_editor", "readme_parser", "diagram_generator", "slack_notifier", "web_search"],
        "max_steps": 15
    },
    "model_router_mothma": {
        "class": "ModelRouterMothmaAgent",
        "module": "agents.model_router_mothma_agent",
        "wake_word": "mothma",
        "tools": ["web_search", "file_editor"],
        "max_steps": 15
    },
    "watcher_wedge": {
        "class": "WatcherWedgeAgent",
        "module": "agents.watcher_wedge_agent",
        "wake_word": "wedge",
        "tools": ["log_reader", "repo_scanner", "backlog_writer", "slack_notifier"],
        "max_steps": 10
    },
    "strategist_sloane": {
        "class": "StrategistSloaneAgent",
        "module": "agents.strategist_sloane_agent",
        "wake_word": "sloane",
        "tools": ["web_search", "diagram_generator", "backlog_writer"],
        "max_steps": 10
    },
    "growth_galen": {
        "class": "GrowthGalenAgent",
        "module": "agents.growth_galen_agent",
        "wake_word": "galen",
        "tools": ["web_search", "slack_notifier", "backlog_writer"],
        "max_steps": 10
    },
    "finance_fennec": {
        "class": "FinanceFennecAgent",
        "module": "agents.finance_fennec_agent",
        "wake_word": "fennec",
        "tools": ["cost_analyzer", "web_search"],
        "max_steps": 10
    }
}
