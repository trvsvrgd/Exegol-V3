import sys
import os
sys.path.insert(0, 'src')
from inference.inference_manager import InferenceManager

llm = InferenceManager.get_client('ollama')
prompt = """Review the following Human-In-The-Loop (HITL) tasks. Identify which ones can be successfully resolved by an autonomous AI Developer Agent (which has access to codebase search, file editing, and terminal commands).
EXCLUDE tasks that explicitly require:
- New physical API keys from third-party dashboards
- Manual system deployment or infrastructure provisioning outside the codebase
- Complex architectural decisions requiring human business context
INCLUDE tasks that are:
- Resolving MOCK or stub code
- Fixing code smells, TODOs, or hardcoded values
- Implementing missing tools or standard codebase integrations
Tasks:
[
    {
        "id": "hitl_research_rex_hardware",
        "task": "Resolve MOCK in src/agents/research_rex_agent.py:L62-L68 - hardware detection hardcoded",
        "category": "mock_code",
        "context": "Hardware detection is currently hardcoded to 16GB VRAM / RTX 4080.",
        "status": "pending"
    }
]
Return a JSON object with a single key "salvageable_ids" mapping to a list of task IDs that the Developer Agent can solve."""
print('Testing Ollama...')
resp = llm.generate(prompt, json_format=True)
print('Response:', resp)
print('Parsed:', llm.parse_json_response(resp))
