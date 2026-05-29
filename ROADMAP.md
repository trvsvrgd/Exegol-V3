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

## Production Readiness Execution Roadmap

This is the production hardening order. A task is not complete until it is backed by deterministic tests and, where applicable, live local smoke evidence from the backend and Workbench UI.

### P0: App Starts, Loads, And Stops Reliably

- [x] Keep startup checks repo-local and Windows-safe through `scripts/verify_startup.py`.
- [x] Release stale backend/frontend ports before launch and during shutdown.
- [x] Start the Workbench frontend in production mode instead of relying on the development server.
- [x] Bind local runtime checks to `127.0.0.1` to avoid localhost/IPv6 ambiguity.
- [x] Make `production_readiness_check.py` verify that the frontend routes actually load, not just that the frontend can build.
- [ ] Add one canonical smoke command that starts backend plus frontend, checks key API/UI routes, and tears them down cleanly.
- [ ] Prove `Start_Exegol.bat` and `Stop_Exegol.bat` can run repeatedly without leaving live listeners on ports `8000` or `3000`.

### P0: Truthful State And Blockers

- [x] Clear stale blocked fleet state during startup preflight.
- [x] Clear stale scheduler heartbeats during startup preflight.
- [x] Archive resolved duplicate/stale backlog failures through `BacklogManager`.
- [x] Prevent resolved crash summaries from remaining visible as live fleet failures.
- [ ] Make every state surface agree: `.exegol/fleet_state.json`, `.exegol/supervisor_state.json`, `.exegol/user_action_required.json`, backlog, and UI operations panels.
- [ ] Separate environment-blocked checks from code regressions in every readiness output.

### P0: Autonomous Loop Progresses

- [x] Persist objective state in `.exegol/objective.json`.
- [x] Add deterministic objective phase transitions for plan, implement, validate, and done.
- [x] Dispatch objective phases to Product Poe, Developer Dex, and Quality Qui-Gon deterministically.
- [x] Fix autonomous handoff RBAC for agents that intentionally trigger follow-on agents.
- [ ] Make `Run Autonomous Fleet` start or resume the objective loop rather than merely run one isolated cycle.
- [ ] Add pause, resume, stop, duplicate-start attach, and loop-status behavior for the selected repo.
- [ ] Prove multiple full loops can complete without corrupting objective or fleet state.

### P0: Crash Containment And Self-Recovery

- [x] Keep Slack notification failures from crashing local fleet work when Slack is disabled or unreachable.
- [x] Keep startup from firing an unbounded missed-job storm.
- [ ] Add bounded retry behavior for provider/model failures and malformed agent output.
- [ ] Ensure supervisor remediation updates blockers and fleet state consistently after backend, frontend, scheduler, Docker, or stale-session failures.
- [ ] Run failure-injection tests for provider timeout, malformed LLM output, Docker unavailable, stale heartbeat, and duplicate starts.

### P1: External Services And Secrets

- [ ] Rotate the exposed Google OAuth credential outside the repo and update local credentials after rotation.
- [ ] Verify Slack bot/app tokens against the real production HITL path.
- [ ] Add explicit environment diagnostics for Slack, Docker, local model provider, and browser/UAT capability.
- [ ] Keep credential files ignored and keep secret findings from printing raw secret values in reports.

### P1: Security And Runtime Guardrails

- [ ] Add outbound URL allowlisting for runtime HTTP probes and web-capable tools.
- [ ] Add prompt-injection handling for scheduled/user prompts before they enter agent execution.
- [ ] Keep destructive filesystem/system permissions behind explicit HITL approval.
- [ ] Add per-agent rate limits, cost ceilings, and loop-budget enforcement.
- [ ] Add tests that RBAC grants are minimal for handoff, filesystem, and destructive permissions.

### P1: Observability And Operator Control

- [ ] Show objective, current phase, active agent, last result, next action, loop count, and blocker reason in the Workbench.
- [ ] Record every objective transition, retry, blocker, remediation, and validation result in `.exegol/objective_events.jsonl`.
- [ ] Add a concise operations timeline that distinguishes current failures from archived history.
- [ ] Add downloadable or copyable readiness reports for local support handoff.

### P2: Release Discipline

- [ ] Keep one documented deterministic local test command passing.
- [ ] Keep frontend lint/build clean.
- [ ] Keep backend compile and targeted readiness tests clean.
- [ ] Keep the working tree understandable by separating generated runtime state from source changes.
- [ ] Document the production runbook: install, launch, stop, verify, recover, rotate secrets, and collect evidence.

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
