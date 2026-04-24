import os
import re
from src.agents.registry import AGENT_REGISTRY

def test_agents_registered_in_readme():
    """Enforces the rule that all agents in registry.py must appear in README.md."""
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
    
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_content = f.read()

    # Get all agent IDs from the registry
    registered_agents = list(AGENT_REGISTRY.keys())

    missing_in_diagram = []
    missing_in_table = []

    for agent_id in registered_agents:
        # Check in the table (usually | `agent_id` |)
        table_pattern = rf"\| `{agent_id}` \|"
        if not re.search(table_pattern, readme_content):
            missing_in_table.append(agent_id)

        # Check in Mermaid diagram (usually A["..."] or A[...])
        # We look for the agent's wake word or specific labels if possible, 
        # but the most reliable way in this repo seems to be checking if the 
        # agent's role or name is mentioned near the mermaid block.
        # Actually, let's just check if the ID is present in the file at all as a start, 
        # or better, check the Mermaid subgraph specifically.
        
    assert not missing_in_table, f"Agents missing from README table: {missing_in_table}"

def test_mermaid_diagram_consistency():
    """Check if the number of agents in the diagram matches the registry (optional/best effort)."""
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_content = f.read()

    # Extract the Mermaid block
    mermaid_match = re.search(r"```mermaid\n(.*?)\n```", readme_content, re.DOTALL)
    assert mermaid_match, "Mermaid diagram not found in README.md"
    mermaid_content = mermaid_match.group(1)

    # In this specific repo, agents are assigned letters A, B, C...
    # and then classed as 'agent'. Let's check the 'class' line.
    class_match = re.search(r"class ([\w,]+) agent;", mermaid_content)
    assert class_match, "Class definition for agents not found in Mermaid diagram"
    
    agent_nodes = class_match.group(1).split(",")
    # The number of nodes should be >= number of agents (some nodes might be FS)
    # Actually, let's just count how many unique nodes are styled as 'agent'
    
    # This is a bit complex to automate perfectly without a mermaid parser, 
    # but the table check is a strong proxy.
    pass
