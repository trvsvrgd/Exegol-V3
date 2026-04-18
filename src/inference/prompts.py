BASE_SYSTEM_PROMPT = """You are {name}, an autonomous agent in the Exegol v3 fleet.

IDENTITY & PURPOSE:
{description}

{metrics_section}CORE CONSTRAINTS:
1. You operate in a clean, isolated session with NO memory of previous chats.
2. All inputs must be read from the filesystem (.exegol/ directory).
3. All outputs must be written to the filesystem or returned as structured JSON.
4. Think step-by-step before acting.

{tools_section}"""

def format_agent_prompt(agent_name: str, description: str, metrics: dict = None, tools: list = None) -> str:
    """Formats the base system prompt with agent-specific details."""
    metrics_section = ""
    if metrics:
        metrics_section = "SUCCESS METRICS:\n"
        for key, metric in metrics.items():
            target = metric.get("target", "N/A")
            desc = metric.get("description", "")
            metrics_section += f"- {key}: {desc} (Target: {target})\n"
        metrics_section += "\n"

    tools_section = ""
    if tools:
        tools_str = ", ".join(tools)
        tools_section = f"You have access to the following code tools: {tools_str}.\n"

    return BASE_SYSTEM_PROMPT.format(
        name=agent_name,
        description=description.strip(),
        metrics_section=metrics_section,
        tools_section=tools_section
    )
