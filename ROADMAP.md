# Exegol v3 Roadmap

## North Star

Make Exegol a reliable, self-sufficient looping system that acts toward one explicit objective until it reaches a verified done state or a truthful human-blocked state.

Production readiness is not defined as "the UI launches" or "agents exist." Production readiness means:

- A user can choose a repo, enter or select one objective, and click `Run Autonomous Fleet`.
- The system persists that objective as durable repo state.
- The orchestrator repeatedly chooses the next necessary action from that objective state.
- Agents execute bounded work, write results, and hand off through explicit state transitions.
- Quality gates verify each implementation step before progress is counted.
- Failures are remediated or surfaced as precise blockers without corrupting the objective state.
- The loop stops only when success criteria are met, the budget is exhausted, or a real human decision is required.

## Priority 0: Objective Loop Reliability

These items supersede broad roadmap work, agent expansion, reporting polish, Slack enhancements, growth/finance automation, and UI-only improvements unless those items directly unblock the objective loop.

1. **Durable Objective Contract**
   - Add `.exegol/objective.json` as the control-plane source of truth.
   - Required fields: `id`, `repo_path`, `goal`, `success_criteria`, `constraints`, `phase`, `active_task_id`, `status`, `loop_count`, `last_agent_id`, `last_result`, `blocked_reason`, `created_at`, `updated_at`.
   - Add migration/defaulting behavior so old repos without an objective are handled cleanly.

2. **Deterministic Loop State Machine**
   - Implement explicit transitions: `idle -> planning -> implementing -> validating -> done`.
   - Add failure transitions: `retrying`, `remediating`, `blocked_human`, `blocked_environment`, `failed_budget`.
   - Reject ambiguous states such as "healthy but blocked" unless a concrete blocker record exists.

3. **Objective-Aware Agent Dispatch**
   - Route each loop step from objective phase and validation state, not generic agent priority alone.
   - Default sequence: Thrawn/Poe for objective clarification and task shaping, Dex for implementation, Qui-Gon for validation, Wedge/Supervisor for remediation, Poe for next task selection.
   - Non-critical agents run only when they support the active objective.

4. **Continuous Run Endpoint**
   - Change `Run Autonomous Fleet` from "start one cycle" to "start/resume objective loop."
   - Add start, pause, resume, stop, and status endpoints for the selected repo/objective.
   - Persist loop ownership so duplicate starts attach to the running loop instead of spawning conflicting work.

5. **Verification Harness**
   - Add deterministic tests proving a seeded objective advances through plan, implement, validate, and done.
   - Add failure-injection tests for provider timeout, malformed LLM output, Docker unavailable, stale heartbeat, and duplicate starts.
   - Keep external/provider/Docker tests quarantined behind explicit markers.

6. **Runtime Observability**
   - Add `.exegol/objective_events.jsonl` for every transition, agent decision, validation result, retry, and blocker.
   - UI should show objective, current phase, current agent, last result, next action, loop count, and blocker reason.

7. **Launch Contract**
   - `Start_Exegol.bat` must start backend and frontend, then `verify_startup.py` must pass.
   - The Workbench must list real Python project repos and start the objective loop for the selected repo.
   - A single canonical deterministic local test command must remain documented and passing.

## Priority 1: Safety For Autonomous Work

These remain important, but they should be sequenced after the objective loop contract exists unless they block it.

- Prompt injection handling for scheduled/user prompts.
- SSRF and outbound URL allowlisting.
- Per-agent rate limiting and cost controls.
- RBAC for destructive tools.
- Secret/key rotation visibility.

## Priority 2: Product Completeness

- Better backlog editing and grooming UI.
- Fleet reporting and weekly summaries.
- Slack/Drive/Gmail integrations.
- Model benchmarking and routing optimization.
- UAT recording and demo artifacts.

## Current Execution Rule

Until Priority 0 is complete, every new roadmap or backlog item should answer: "Does this make the selected repo/objective loop more reliable?" If not, it is secondary.
