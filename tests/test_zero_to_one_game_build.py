import os

from tools.agentic_coding import execute_coding_task
from tools.objective_manager import ObjectiveManager
from tools.prompt_generator import ZERO_TO_ONE_GAME_MARKER, generate_active_prompt


class FailingPlanner:
    def generate(self, *args, **kwargs):
        return "not json"


class PartialPlanner:
    def generate(self, *args, **kwargs):
        return """
        [
          {"type": "write", "path": "README.md", "content": "# Partial", "reason": "partial docs"},
          {"type": "write", "path": "index.html", "content": "<script src='src/game.js'></script>", "reason": "partial shell"},
          {"type": "write", "path": "styles.css", "content": "body{}", "reason": "partial styles"}
        ]
        """


class UnusedPromptClient:
    def generate(self, *args, **kwargs):
        raise AssertionError("zero-to-one prompt generation should not call the LLM")


def test_zero_to_one_prompt_is_actionable_for_game_repo(tmp_path):
    ObjectiveManager(str(tmp_path)).create_or_update(
        goal="Build a browser puzzle game for the AI team demo.",
        success_criteria=["Playable loop with score and restart."],
        constraints=["No paid APIs or external assets."],
    )

    result = generate_active_prompt(
        {
            "id": "zero_to_one_build",
            "summary": "Build the first runnable version.",
            "source_agent": "zero_to_one_onboarding",
        },
        str(tmp_path),
        UnusedPromptClient(),
        "system",
    )

    prompt = result["prompt"]
    assert result["success"] is True
    assert ZERO_TO_ONE_GAME_MARKER in prompt
    assert "index.html" in prompt
    assert "src/game.js" in prompt
    assert "No paid APIs or external assets." in prompt
    assert "playable loop" in prompt.lower()


def test_zero_to_one_game_fallback_scaffolds_playable_static_app(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.agentic_coding.web_search", lambda *args, **kwargs: [])

    result = execute_coding_task(
        task_description=(
            "# Active Developer Task\n"
            f"**Marker:** {ZERO_TO_ONE_GAME_MARKER}\n"
            "Build a browser puzzle game for the AI team demo."
        ),
        repo_path=str(tmp_path),
        llm_client=FailingPlanner(),
        agent_name="DeveloperDexAgent",
        system_prompt="system",
        max_steps=10,
        session_id="zero_to_one_test",
    )

    assert "Coding cycle complete" in result["summary"]
    assert "Write index.html" in result["summary"]
    assert "Write src/game.js" in result["summary"]
    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "styles.css").exists()
    assert (tmp_path / "src" / "game.js").exists()
    assert (tmp_path / "README.md").exists()

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    js = (tmp_path / "src" / "game.js").read_text(encoding="utf-8")
    assert "Signal Grid" in html
    assert "Victory" in js
    assert "window.setTimeout(nextRound" in js


def test_zero_to_one_game_fallback_replaces_incomplete_valid_plan(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.agentic_coding.web_search", lambda *args, **kwargs: [])

    result = execute_coding_task(
        task_description=(
            "# Active Developer Task\n"
            f"**Marker:** {ZERO_TO_ONE_GAME_MARKER}\n"
            "Build a browser puzzle game for the AI team demo."
        ),
        repo_path=str(tmp_path),
        llm_client=PartialPlanner(),
        agent_name="DeveloperDexAgent",
        system_prompt="system",
        max_steps=10,
        session_id="zero_to_one_partial_test",
    )

    assert "Write src/game.js" in result["summary"]
    assert (tmp_path / "src" / "game.js").exists()
    assert "Signal Grid" in (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Victory" in (tmp_path / "src" / "game.js").read_text(encoding="utf-8")
