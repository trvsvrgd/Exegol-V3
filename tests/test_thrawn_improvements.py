import os
import json
import pytest
from inference.inference_manager import InferenceManager
from inference.llm_client import GeminiClient, AnthropicClient, OllamaClient
from tools.thrawn_intel_manager import ThrawnIntelManager
from tools.hitl_manager import HITLManager
from tools.state_manager import StateManager
from tools.backlog_manager import BacklogManager
from agents.product_poe_agent import ProductPoeAgent


class MalformedSalvageClient:
    def generate_system_prompt(self, agent):
        return "system"

    def generate(self, prompt, system_instruction=None, json_format=False):
        return "[]"

    def parse_json_response(self, response):
        return []

def test_inference_manager_routing():
    # Test that model strings are routed to the correct client classes
    # 1. Gemini
    client = InferenceManager.get_client(provider="gemini-2.0-flash")
    assert isinstance(client, GeminiClient)
    assert client.model == "gemini-2.0-flash"

    client2 = InferenceManager.get_client(provider="gemini")
    assert isinstance(client2, GeminiClient)
    assert client2.model == "gemini-2.0-flash" # default

    # 2. Claude/Anthropic
    client3 = InferenceManager.get_client(provider="claude-3-5-sonnet")
    assert isinstance(client3, AnthropicClient)
    assert client3.model == "claude-3-5-sonnet"

    client4 = InferenceManager.get_client(provider="anthropic")
    assert isinstance(client4, AnthropicClient)

    # 3. Ollama fallback
    client5 = InferenceManager.get_client(provider="ollama")
    assert isinstance(client5, OllamaClient)

    client6 = InferenceManager.get_client(provider="my-custom-local-model")
    assert isinstance(client6, OllamaClient)
    assert client6.model == "my-custom-local-model"

def test_hitl_auto_resolution(tmp_path):
    repo_path = str(tmp_path)
    exegol_dir = tmp_path / ".exegol"
    exegol_dir.mkdir(exist_ok=True)

    # Setup a pending HITL task matching a question
    question = "What is the primary target?"
    
    # 1. Using StateManager to create the task
    sm = StateManager(repo_path)
    sm.add_hitl_task(
        summary=f"Thrawn: {question[:60]}...",
        category="intent",
        context=f"Thoughtful Thrawn requires project clarity: '{question}'\n\nPlease answer in .exegol/intent.md or the Workbench.",
        task_id="test-task-123"
    )

    # Verify task exists and is pending
    hitl_mgr = HITLManager(repo_path)
    pending = hitl_mgr.get_pending()
    assert len(pending) == 1
    assert pending[0]["id"] == "test-task-123"
    assert pending[0]["status"] == "pending"

    # Let's import ThrawnIntelManager and verify it writes the answer
    intel_mgr = ThrawnIntelManager(repo_path)
    intel_mgr.answer_question(question, "We target the core system.")
    
    # Resolve the HITL task (mirrors our updated api.py code)
    pending_tasks = hitl_mgr.get_pending()
    for task in pending_tasks:
        context = task.get("context", "")
        task_title = task.get("task", "")
        is_match = False
        if question in context:
            is_match = True
        elif task_title.startswith("Thrawn: ") and question.startswith(task_title[8:].rstrip(".")):
            is_match = True
        
        if is_match:
            hitl_mgr.resolve_task(
                item_id=task.get("id"),
                status="done",
                notes="Answered"
            )

    # Verify task is resolved
    pending_after = hitl_mgr.get_pending()
    assert len(pending_after) == 0

    all_tasks = hitl_mgr.get_queue()
    assert len(all_tasks) == 1
    assert all_tasks[0]["status"] == "done"


def test_product_poe_ignores_malformed_salvage_response(tmp_path):
    sm = StateManager(str(tmp_path))
    sm.add_hitl_task(
        summary="Resolve implementation detail",
        category="limitation",
        context="Developer-solvable task.",
        task_id="hitl_malformed",
    )

    agent = ProductPoeAgent(MalformedSalvageClient())
    agent._salvage_hitl_tasks(str(tmp_path), BacklogManager(str(tmp_path)))

    queue = HITLManager(str(tmp_path)).get_queue()
    assert queue[0]["status"] == "pending"
    assert not (tmp_path / ".exegol" / "backlog.json").exists()
