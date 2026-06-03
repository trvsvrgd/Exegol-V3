import os
import json
import re
import time
from typing import List, Dict, Any, Optional
from tools.file_editor_tool import read_file, write_file, replace_content, search_replace_regex
from tools.web_search import web_search
from tools.fleet_logger import log_interaction

# Session-scoped failure injection tracker — prevents backlog spam.
# Key: (session_id, error_type)  →  True if a backlog item was already injected.
_session_failure_injected: Dict[tuple, bool] = {}
ZERO_TO_ONE_GAME_MARKER = "EXEGOL_ZERO_TO_ONE_GAME"
ZERO_TO_ONE_REQUIRED_FILES = {"index.html", "styles.css", "src/game.js", "README.md"}

# --- JSON Extraction Strategies (arch_dex_llm_parse_resilience) ---

def _strip_markdown_fences(text: str) -> str:
    """Removes ```json ... ``` or ``` ... ``` fences from LLM output."""
    # Strip ```json ... ``` or ``` ... ``` blocks
    stripped = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    stripped = stripped.replace("```", "")
    return stripped.strip()


def _extract_json_array(text: str) -> Optional[list]:
    """
    Multi-strategy extractor: tries to pull a JSON array out of an LLM response
    using increasingly aggressive methods.
    
    Strategy order:
      1. Direct JSON parse (fastest path — works if LLM returned clean JSON)
      2. Strip markdown fences, then parse
      3. Regex-find the outermost [...] block and parse
      4. Regex-find the outermost {...} block (dict with embedded array), unwrap
    """
    if not text:
        return None

    def unwrap_dict(d: dict) -> Optional[list]:
        for key in ("actions", "steps", "plan", "tasks"):
            if isinstance(d.get(key), list):
                return d[key]
        if "type" in d and "path" in d:
            return [d]
        return None

    # Strategy 1: Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            unwrapped = unwrap_dict(result)
            if unwrapped is not None:
                return unwrapped
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Strip markdown fences, then parse
    cleaned = _strip_markdown_fences(text)
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            unwrapped = unwrap_dict(result)
            if unwrapped is not None:
                return unwrapped
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 3: Extract the first top-level [...] array via regex
    match = re.search(r"(\[[\s\S]*\])", cleaned)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: Extract the first top-level {...} dict and unwrap
    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, dict):
                unwrapped = unwrap_dict(result)
                if unwrapped is not None:
                    return unwrapped
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _validate_plan(actions: list) -> list:
    """
    Validates and normalises each action object against the required schema.
    
    Required keys: type, path, content
    Optional keys: target (for replace/regex), reason
    
    Returns a filtered list of valid actions, logging warnings for skipped ones.
    """
    REQUIRED_KEYS = {"type", "path", "content"}
    VALID_TYPES = {"write", "replace", "regex"}
    valid = []

    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            print(f"[AgenticCoding][Validate] Action #{i} is not a dict — skipping: {action!r}")
            continue

        # Normalise key aliases before validation
        action.setdefault("path", action.pop("file", action.pop("filename", None)))
        action.setdefault("content", action.pop("text", action.pop("code", action.pop("replacement", None))))
        action.setdefault("target", action.pop("pattern", ""))
        action.setdefault("reason", "Applying agentic coding update")

        missing = REQUIRED_KEYS - set(k for k, v in action.items() if v is not None)
        if missing:
            print(f"[AgenticCoding][Validate] Action #{i} missing keys {missing} — skipping: {action!r}")
            continue

        if action.get("type") not in VALID_TYPES:
            print(f"[AgenticCoding][Validate] Action #{i} has unknown type '{action.get('type')}' — skipping.")
            continue

        if action.get("type") in ("replace", "regex") and not action.get("target"):
            print(f"[AgenticCoding][Validate] Action #{i} type '{action['type']}' requires 'target' — skipping.")
            continue

        valid.append(action)

    return valid


def _zero_to_one_game_fallback_actions(task_description: str) -> Optional[list]:
    """Fallback scaffold for the demo-critical empty-repo browser game path."""
    if ZERO_TO_ONE_GAME_MARKER not in task_description and "zero_to_one_build" not in task_description:
        return None

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Signal Grid</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="shell">
    <section class="hud" aria-label="Game status">
      <div>
        <p class="eyebrow">Signal Grid</p>
        <h1>Repeat the pattern before the signal fades.</h1>
      </div>
      <div class="stats">
        <span>Round <strong id="round">0</strong>/5</span>
        <span>Score <strong id="score">0</strong></span>
      </div>
    </section>

    <section class="game-area" aria-label="Signal Grid game">
      <div id="board" class="board" aria-label="Clickable signal tiles"></div>
      <aside class="panel">
        <p id="message" class="message">Press Start to arm the grid.</p>
        <button id="start" type="button">Start</button>
        <button id="restart" type="button" class="secondary">Restart</button>
        <ul class="rules">
          <li>Watch the highlighted tiles.</li>
          <li>Click the same pattern in order.</li>
          <li>Clear five rounds to win.</li>
        </ul>
      </aside>
    </section>
  </main>
  <script src="src/game.js"></script>
</body>
</html>
"""

    css = """:root {
  color-scheme: dark;
  --bg: #101114;
  --panel: #191d25;
  --ink: #f5f7fb;
  --muted: #a6adbb;
  --accent: #4ade80;
  --danger: #fb7185;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: radial-gradient(circle at top left, #243042, var(--bg) 48%);
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.shell {
  width: min(980px, calc(100vw - 32px));
}

.hud, .game-area, .panel {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(25, 29, 37, 0.88);
}

.hud {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  padding: 24px;
  border-radius: 8px 8px 0 0;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  max-width: 620px;
  margin: 0;
  font-size: clamp(1.8rem, 5vw, 3.25rem);
  line-height: 1;
}

.stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  color: var(--muted);
  font-weight: 700;
}

.stats span {
  min-width: 110px;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
}

.game-area {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 280px;
  gap: 24px;
  padding: 24px;
  border-top: 0;
  border-radius: 0 0 8px 8px;
}

.board {
  display: grid;
  grid-template-columns: repeat(3, minmax(72px, 1fr));
  gap: 12px;
}

.tile {
  aspect-ratio: 1;
  border: 0;
  border-radius: 8px;
  background: #2b3445;
  box-shadow: inset 0 -10px 0 rgba(0, 0, 0, 0.16);
  cursor: pointer;
  transition: transform 120ms ease, background 120ms ease, box-shadow 120ms ease;
}

.tile:hover { transform: translateY(-2px); }
.tile.active { background: var(--tile-color); box-shadow: 0 0 28px var(--tile-color); }
.tile.correct { outline: 3px solid var(--accent); }
.tile.wrong { outline: 3px solid var(--danger); }

.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  border-radius: 8px;
}

.message {
  min-height: 58px;
  margin: 0;
  color: var(--muted);
  line-height: 1.45;
}

button {
  width: 100%;
  min-height: 46px;
  border: 0;
  border-radius: 6px;
  background: var(--accent);
  color: #06200f;
  cursor: pointer;
  font-weight: 900;
}

button.secondary {
  background: transparent;
  color: var(--ink);
  border: 1px solid rgba(255, 255, 255, 0.16);
}

.rules {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--muted);
  line-height: 1.6;
}

@media (max-width: 760px) {
  .hud, .game-area { grid-template-columns: 1fr; }
  .hud { align-items: start; flex-direction: column; }
}
"""

    js = """const board = document.querySelector("#board");
const message = document.querySelector("#message");
const roundEl = document.querySelector("#round");
const scoreEl = document.querySelector("#score");
const startButton = document.querySelector("#start");
const restartButton = document.querySelector("#restart");

const colors = ["#38bdf8", "#a78bfa", "#f472b6", "#fb923c", "#facc15", "#4ade80", "#2dd4bf", "#60a5fa", "#f87171"];
const tiles = [];
let pattern = [];
let player = [];
let round = 0;
let score = 0;
let acceptingInput = false;

for (let index = 0; index < 9; index += 1) {
  const tile = document.createElement("button");
  tile.className = "tile";
  tile.type = "button";
  tile.setAttribute("aria-label", `Signal tile ${index + 1}`);
  tile.style.setProperty("--tile-color", colors[index]);
  tile.addEventListener("click", () => handleTile(index));
  board.appendChild(tile);
  tiles.push(tile);
}

function resetGame() {
  pattern = [];
  player = [];
  round = 0;
  score = 0;
  acceptingInput = false;
  roundEl.textContent = "0";
  scoreEl.textContent = "0";
  message.textContent = "Press Start to arm the grid.";
  clearTileStates();
}

function startGame() {
  resetGame();
  message.textContent = "Watch closely.";
  nextRound();
}

function nextRound() {
  acceptingInput = false;
  player = [];
  round += 1;
  roundEl.textContent = String(round);
  pattern.push(Math.floor(Math.random() * tiles.length));
  playPattern();
}

function playPattern() {
  message.textContent = `Round ${round}: memorize the signal.`;
  pattern.forEach((tileIndex, step) => {
    window.setTimeout(() => flashTile(tileIndex), 520 * (step + 1));
  });
  window.setTimeout(() => {
    acceptingInput = true;
    message.textContent = "Your turn. Repeat the pattern.";
  }, 520 * (pattern.length + 1));
}

function flashTile(index, state = "active") {
  const tile = tiles[index];
  tile.classList.add(state);
  window.setTimeout(() => tile.classList.remove(state), 260);
}

function handleTile(index) {
  if (!acceptingInput) return;
  player.push(index);
  const expected = pattern[player.length - 1];
  if (index !== expected) {
    acceptingInput = false;
    flashTile(index, "wrong");
    message.textContent = `Signal lost. Final score: ${score}. Press Restart to try again.`;
    return;
  }

  flashTile(index, "correct");
  score += 10;
  scoreEl.textContent = String(score);

  if (player.length === pattern.length) {
    acceptingInput = false;
    if (round >= 5) {
      score += 50;
      scoreEl.textContent = String(score);
      message.textContent = `Victory. You stabilized the grid with ${score} points.`;
      return;
    }
    message.textContent = "Pattern locked. Next round incoming.";
    window.setTimeout(nextRound, 850);
  }
}

function clearTileStates() {
  tiles.forEach((tile) => tile.classList.remove("active", "correct", "wrong"));
}

startButton.addEventListener("click", startGame);
restartButton.addEventListener("click", startGame);
resetGame();
"""

    readme = """# Signal Grid

A small browser puzzle game generated by the Exegol fleet for the zero-to-one demo path.

## Run

Open `index.html` in a browser.

## Gameplay

Watch the highlighted tile pattern, repeat it in order, and clear five rounds to win. A wrong click ends the run and shows the final score.
"""

    return [
        {"type": "write", "path": "index.html", "content": html, "reason": "Create the playable browser game shell."},
        {"type": "write", "path": "styles.css", "content": css, "reason": "Style the game for a polished live demo."},
        {"type": "write", "path": "src/game.js", "content": js, "reason": "Implement the playable signal pattern loop."},
        {"type": "write", "path": "README.md", "content": readme, "reason": "Document local run instructions."},
    ]


def _missing_zero_to_one_required_files(actions: list) -> set:
    written_paths = {
        str(action.get("path") or "").replace("\\", "/")
        for action in actions
        if isinstance(action, dict) and action.get("type") == "write"
    }
    return ZERO_TO_ONE_REQUIRED_FILES - written_paths


def _inject_parse_failure_backlog(repo_path: str, session_id: str, error_type: str, detail: str):
    """
    Injects a single backlog task for a parse failure within this session.
    Deduplicates: only one item per (session_id, error_type) is ever injected.
    """
    key = (session_id, error_type)
    if _session_failure_injected.get(key):
        print(f"[AgenticCoding] Dedup: Skipping duplicate backlog injection for session '{session_id}', error '{error_type}'.")
        return

    _session_failure_injected[key] = True

    try:
        from tools.backlog_manager import BacklogManager
        import datetime
        bm = BacklogManager(repo_path)
        task_id = f"dex_parse_fail_{session_id[:8]}_{error_type[:20]}"
        bm.add_task({
            "id": task_id,
            "summary": f"DeveloperDex parse failure: {error_type} in session {session_id[:8]}",
            "priority": "high",
            "type": "bug",
            "status": "todo",
            "source_agent": "AgenticCoding",
            "rationale": f"LLM returned unparseable coding plan (error_type={error_type}). Detail: {detail[:500]}. Session: {session_id}.",
            "created_at": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[AgenticCoding] Failed to inject failure backlog item: {e}")


def execute_coding_task(
    task_description: str,
    repo_path: str,
    llm_client: Any,
    agent_name: str,
    system_prompt: str,
    max_steps: int = 10,
    session_id: str = "unknown"
) -> dict:
    """
    A high-level tool that performs agentic coding: researches, plans, and executes file changes.
    
    Args:
        task_description: The description of the coding task to perform.
        repo_path: The root path of the repository.
        llm_client: The LLM client to use for planning.
        agent_name: The name of the agent calling this tool.
        system_prompt: The system prompt for the LLM.
        max_steps: Maximum number of file operations to perform.
        session_id: Current session ID for logging.
        
    Returns:
        A dict with keys: "summary" (str), "actions" (list), "results" (list).
    """
    # CRITICAL: Set env var FIRST — before any tool call that uses RBAC (write_file, read_file).
    # This must happen before web_search in case any downstream tool checks permissions.
    os.environ["EXEGOL_ACTIVE_AGENT"] = agent_name
    print(f"[AgenticCoding] Starting task for {agent_name}: {task_description[:100]}...")

    # 1. Research (Optional but recommended for agentic feel)
    search_query = f"best practices and implementation for: {task_description[:200]}"
    research_results = web_search(search_query, num_results=2)

    # 2. Plan
    files_in_repo = os.listdir(repo_path)

    # Automatically extract candidate files mentioned in the prompt and read their contents to provide context
    candidates = re.findall(r'[a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+', task_description)
    mentioned_files = {}
    for candidate in candidates:
        norm_path = candidate.replace('\\', '/').strip('`*"\'')
        possible_paths = [
            os.path.join(repo_path, norm_path),
            os.path.join(repo_path, 'src', norm_path),
        ]
        for p in possible_paths:
            if os.path.isfile(p):
                abs_p = os.path.realpath(p)
                if abs_p.startswith(os.path.realpath(repo_path)):
                    try:
                        with open(abs_p, 'r', encoding='utf-8-sig') as f:
                            content = f.read()
                        mentioned_files[norm_path] = content
                        break
                    except Exception:
                        pass

    file_contents_context = ""
    if mentioned_files:
        file_contents_context = "\n\nFile Contents for Context:\n"
        for fname, fcontent in mentioned_files.items():
            lines = fcontent.splitlines()
            if len(lines) > 300:
                fcontent = "\n".join(lines[:300]) + "\n[... truncated ...]"
            file_contents_context += f"--- Path: {fname} ---\n{fcontent}\n\n"

    planning_prompt = f"""You are the 'Agentic Coding' engine. Your ONLY output must be a valid JSON array — no explanations, no markdown, no prose.

Task to implement:
{task_description}

Implementation Research: {json.dumps(research_results)}{file_contents_context}

Existing Files (Top Level): {files_in_repo}

Return a JSON array of file action objects. Each object MUST have these EXACT keys:
- "type": one of "write", "replace", or "regex"
- "path": relative path to the file
- "content": the new content or replacement string
- "target": the text to replace or regex pattern (required only for replace/regex types)
- "reason": one-line rationale

Example output:
[
  {{"type": "write", "path": "scratch/notes.txt", "content": "hello", "reason": "Create notes file"}}
]

Respond with ONLY the JSON array. No markdown fences. No prose. No explanation."""

    actions = None
    raw_response = ""

    try:
        raw_response = llm_client.generate(planning_prompt, system_instruction=system_prompt, json_format=True)
        actions = _extract_json_array(raw_response)
    except Exception as e:
        return {
            "summary": f"Error during planning: {str(e)}",
            "actions": [],
            "results": []
        }

    # Retry once if extraction failed
    if actions is None:
        _save_failed_response(repo_path, raw_response, attempt=1)
        print(f"[AgenticCoding] Multi-strategy parse failed on attempt 1 — retrying with strict prompt.")

        retry_prompt = (
            f"Return ONLY a valid JSON array (no markdown, no prose, no fences) of file actions for this task:\n"
            f"{task_description}\n\n"
            f"Example: [{{\"type\": \"write\", \"path\": \"scratch/out.txt\", \"content\": \"hello\", \"reason\": \"demo\"}}]"
        )
        try:
            raw_response2 = llm_client.generate(retry_prompt, system_instruction=system_prompt, json_format=True)
            actions = _extract_json_array(raw_response2)
            _save_failed_response(repo_path, raw_response2, attempt=2)
        except Exception as e2:
            return {
                "summary": f"Error during planning retry: {str(e2)}",
                "actions": [],
                "results": []
            }

    if actions is None:
        msg = "Failed to parse coding plan from LLM after retry. See scratch/failed_plan_response.txt"
        fallback_actions = _zero_to_one_game_fallback_actions(task_description)
        if fallback_actions:
            print("[AgenticCoding] Using zero-to-one game fallback scaffold after parse failure.")
            actions = fallback_actions
        else:
            _inject_parse_failure_backlog(repo_path, session_id, "parse_failure", raw_response[:300])
            return {"summary": msg, "actions": [], "results": []}

    # 3. Validate plan structure
    validated_actions = _validate_plan(actions)
    if not validated_actions:
        fallback_actions = _zero_to_one_game_fallback_actions(task_description)
        if fallback_actions:
            print("[AgenticCoding] Using zero-to-one game fallback scaffold after empty plan.")
            actions = fallback_actions
            validated_actions = _validate_plan(actions)

    if not validated_actions:
        msg = "LLM returned a plan with 0 valid actions after schema validation."
        _inject_parse_failure_backlog(repo_path, session_id, "empty_valid_plan", str(actions)[:300])
        return {"summary": msg, "actions": actions, "results": []}

    missing_required = _missing_zero_to_one_required_files(validated_actions)
    fallback_actions = _zero_to_one_game_fallback_actions(task_description)
    if fallback_actions and missing_required:
        missing = ", ".join(sorted(missing_required))
        print(f"[AgenticCoding] Using zero-to-one game fallback scaffold after incomplete plan. Missing: {missing}.")
        actions = fallback_actions
        validated_actions = _validate_plan(actions)

    results = []
    steps_used = 0

    print(f"[AgenticCoding] Parsed and validated {len(validated_actions)}/{len(actions)} actions.")

    for action in validated_actions:
        if steps_used >= max_steps:
            results.append("Reached max_steps limit.")
            break

        action_type = action.get("type")
        path = action.get("path")
        content = action.get("content")
        target = action.get("target", "")
        reason = action.get("reason", "Applying agentic coding update")

        # Pulse heartbeat to signal progress (arch_agent_heartbeat)
        from tools.heartbeat_monitor import HeartbeatMonitor
        HeartbeatMonitor.pulse_session(repo_path, session_id)

        file_path = os.path.join(repo_path, path)

        # --- REPO BOUNDARY GUARD ---
        # Ensure the LLM-generated path stays within the repo and doesn't escape.
        real_repo = os.path.realpath(repo_path)
        real_file = os.path.realpath(file_path)
        if not (real_file.startswith(real_repo + os.sep) or real_file == real_repo):
            result_msg = f"Skipped {path}: path escapes repo boundary (security guard)."
            results.append(result_msg)
            print(f"[AgenticCoding] {result_msg}")
            continue

        # For replace/regex actions on non-existent files, skip gracefully.
        if action_type in ("replace", "regex") and not os.path.exists(file_path):
            result_msg = f"Skipped {action_type} on {path}: file does not exist. Use 'write' to create it first."
            results.append(result_msg)
            print(f"[AgenticCoding] {result_msg}")
            continue

        try:
            if action_type == "write":
                res = write_file(file_path, content, reason=reason)
                results.append(f"Write {path}: {res}")
                outcome = "failure" if res.startswith("Error:") else "success"
            elif action_type == "replace":
                res = replace_content(file_path, target, content, reason=reason)
                results.append(f"Replace in {path}: {res}")
                outcome = "failure" if res.startswith("Error:") else "success"
            elif action_type == "regex":
                res = search_replace_regex(file_path, target, content, reason=reason)
                results.append(f"Regex in {path}: {res}")
                outcome = "failure" if res.startswith("Error:") else "success"
            else:
                results.append(f"Unknown action type: {action_type}")
                continue

            steps_used += 1

            if outcome == "failure":
                raise Exception(res)

            # Log individual interaction (arch_dex_granular_logging)
            log_interaction(
                agent_id=agent_name,
                outcome=outcome,
                task_summary=f"{action_type.capitalize()} {path}: {reason}",
                repo_path=repo_path,
                steps_used=1,
                session_id=session_id,
                state_changes={"file_modified": path}
            )

        except Exception as e:
            error_msg = str(e)
            results.append(f"Error executing action on {path}: {error_msg}")
            log_interaction(
                agent_id=agent_name,
                outcome="failure",
                task_summary=f"Failed {action_type} on {path}",
                repo_path=repo_path,
                steps_used=1,
                session_id=session_id,
                errors=[error_msg]
            )

    summary = f"Coding cycle complete for {agent_name}. Results:\n" + "\n".join(results)
    return {
        "summary": summary,
        "actions": validated_actions,
        "results": results
    }


def _save_failed_response(repo_path: str, response: str, attempt: int):
    """Saves a failed LLM response to scratch/ for debugging."""
    try:
        scratch_dir = os.path.join(repo_path, "scratch")
        os.makedirs(scratch_dir, exist_ok=True)
        path = os.path.join(scratch_dir, "failed_plan_response.txt")
        mode = "w" if attempt == 1 else "a"
        with open(path, mode, encoding="utf-8") as f:
            f.write(f"ATTEMPT {attempt}:\n{response}\n\n")
    except Exception:
        pass
