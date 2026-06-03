import json
import os
from typing import Dict, Any

from tools.objective_manager import ObjectiveManager


ZERO_TO_ONE_TASK_ID = "zero_to_one_build"
ZERO_TO_ONE_GAME_MARKER = "EXEGOL_ZERO_TO_ONE_GAME"

def generate_active_prompt(task: Dict[str, Any], repo_path: str, llm_client, system_prompt: str) -> Dict[str, Any]:
    """Standardized tool to context-enrich a task into a detailed developer instruction set.
    
    Args:
        task: The task object from the backlog.
        repo_path: Path to the target repository.
        llm_client: Client used for inference.
        system_prompt: The calling agent's system prompt.

    Returns:
        Dict: {
            "prompt": str,
            "success": bool,
            "error": str | None
        }
    """
    print(f"[PromptGenerator] Researching feasibility and context for: {task.get('summary')}")

    if task.get("id") == ZERO_TO_ONE_TASK_ID or task.get("source_agent") == "zero_to_one_onboarding":
        return _generate_zero_to_one_prompt(task, repo_path)
    
    # 1. Research phase
    from tools.web_search import web_search
    search_query = f"technical implementation details and best practices for: {task.get('summary')}"
    research = web_search(search_query, num_results=2)
    
    # 2. Enrichment phase
    context_prompt = f"""
    Expand this task into a detailed developer instruction set.
    Task Summary: {task.get('summary')}
    Task Description: {task.get('description', 'N/A')}
    Repository: {repo_path}
    
    Implementation Research Context:
    {json.dumps(research, indent=2)}
    
    Your output should include:
    1. A clear implementation plan.
    2. Specific files to analyze or modify.
    3. Potential risks or technical debt to watch for.

    Format as Markdown.
    """
    
    try:
        response = llm_client.generate(context_prompt, system_instruction=system_prompt)
        full_prompt = f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n{response}"
        return {
            "prompt": full_prompt,
            "success": True,
            "error": None
        }
    except Exception as e:
        error_msg = f"Failed to generate prompt: {str(e)}"
        print(f"[PromptGenerator] {error_msg}")
        # Fallback to a simple prompt
        fallback_prompt = f"# Active Developer Task\n\n**Task ID:** {task.get('id')}\n\n## Instructions\n{task.get('summary')}\n"
        return {
            "prompt": fallback_prompt,
            "success": False,
            "error": error_msg
        }


def _generate_zero_to_one_prompt(task: Dict[str, Any], repo_path: str) -> Dict[str, Any]:
    objective = ObjectiveManager(repo_path).load()
    goal = objective.get("goal") or task.get("summary") or "Build the first runnable app."
    success_criteria = objective.get("success_criteria") or []
    constraints = objective.get("constraints") or []

    prompt = f"""# Active Developer Task

**Task ID:** {task.get('id')}
**Marker:** {ZERO_TO_ONE_GAME_MARKER}

## Goal
{goal}

## Success Criteria
{_markdown_list(success_criteria)}

## Human Constraints
{_markdown_list(constraints)}

## Build Instructions
Create the first playable version directly in this empty repository. The demo target is a browser game that can run locally without build tooling.

Required files:
- `index.html`
- `styles.css`
- `src/game.js`
- `README.md`

Non-negotiables:
- Use vanilla HTML, CSS, and JavaScript.
- Do not use CDNs, external assets, network calls, paid APIs, or placeholder gameplay.
- The game must have a complete playable loop, visible controls, score/progress feedback, win/loss states, and a restart path.
- The first screen should be the actual game, not a marketing page.
- Keep the implementation small enough to inspect live during a knowledge-sharing demo.
- Include README run instructions for opening `index.html` directly.

Recommended concept if the human did not specify one: a polished tile-based puzzle game named Signal Grid, where the player watches a pattern, repeats it, scores rounds, and wins after a short sequence.
"""
    return {
        "prompt": prompt,
        "success": True,
        "error": None,
    }


def _markdown_list(items):
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return "- None specified."
    return "\n".join(f"- {item}" for item in cleaned)
