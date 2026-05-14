# 🌌 Exegol v3 — Autonomous Multi-Agent Dev Fleet

> **The first fully stateless, filesystem-driven autonomous agent fleet for software development.**
> No shared memory. No long-running sessions. Just a directory, a backlog, and a fleet of specialized AI agents that never sleep.

Exegol v3 is a proposed novel paradigm in autonomous software engineering. Forget monolithic AI assistants or brittle pipeline scripts — Exegol is a living, breathing fleet of purpose-built agents that collaboratively plan, design, build, test, and document software *continuously*, across any number of repositories, without human intervention.

Each agent in the fleet is **stateless by design**. Instead of relying on fragile long-context memory or shared process state, Exegol uses the **FileSystem as State** — a `.exegol/` directory that acts as the single source of truth. Agents wake up, read the current state, execute their specialty, write their output, and hand off to the next agent. No deadlocks. No context drift. No hallucinated history.

The result: a **self-sustaining development loop** that can be triggered with a single word — `go`.

---

## 🔄 Agent Handoff Loop

The Exegol ecosystem operates on a non-cyclical, state-driven loop. Each agent wakes up, performs a task based on the current state of the `.exegol/` directory, and hands off the next step by updating the backlog or other state files.

```mermaid
flowchart TD
    subgraph Initialization
    A["🔵 Onboarding Thrawn"] -- "Captures Intent" --> FS[("📁 .exegol Context")]
    V["🔴 Vibe Vader"] -- "Identifies Human Actions" --> FS
    end

    subgraph Strategy_and_Planning ["Strategy & Planning"]
    direction TB
    FS -- "Strategy" --> S["🧠 Strategist Sloane"]
    S -- "Briefs" --> G["📈 Growth Galen"]
    G -- "GTM" --> FF["💰 Finance Fennec"]
    FF -- "Economics" --> FS
    end

    subgraph Product_Design ["Product & Design"]
    direction TB
    FS -- "Concept" --> B["⚪ Product Poe"]
    B -- "Tasks" --> C["🤖 Architect Artoo"]
    C -- "Designs" --> FS
    end

    subgraph Build_and_Verify ["Implementation & Quality"]
    direction TB
    FS -- "Instructions" --> D["👨🔧 Developer Dex"]
    D -- "Implementation" --> FS
    FS -- "Validation" --> E["⚔️ Quality Qui-Gon"]
    E -- "Pass" --> FS
    E -- "Fail" --> B
    end

    subgraph Polish_Assets ["Polish & Evidence"]
    direction TB
    FS -- "Documentation" --> H["🟪 Markdown Mace"]
    H -- "Markdown" --> FS
    end

    subgraph Oversight_Systems ["Oversight & Intelligence"]
    direction TB
    FS -- "Telemetry" --> J["💪 Optimizer Ahsoka"]
    J -- "Optimization" --> B
    FS -- "Reviews" --> K["🦍 Chief of Staff Chewie"]
    K -- "Scorecards" --> Report
    FS -- "Metrics" --> L["🎭 Report Revan"]
    L -- "Summaries" --> Report
    FS -- "Costs" --> M["🧠 Intel Ima"]
    M -- "FinOps" --> FF
    Report[("📧 Intelligence Reports")]
    end

    classDef agent fill:#f9f9f9,stroke:#333,stroke-width:2px;
    class A,B,C,D,E,F,G,H,J,K,L,M,N,O,P,V,TT,MRM,S,G,FF agent;
```

## 🤖 The Agent Fleet

| Agent ID | Alliterative Name | Core Responsibility | Primary Handoff Output |
| :--- | :--- | :--- | :--- |
| `thoughtful_thrawn` | Thoughtful Thrawn | Onboarding & User Intent | `.exegol/backlog.json` |
| `strategist_sloane` | Strategist Sloane | Market Intelligence & Business Strategy | `.exegol/strategy_brief.md` |
| `growth_galen` | Growth Galen | GTM Strategy & Outreach | `.exegol/gtm_plan.md` |
| `finance_fennec` | Finance Fennec | Economic Modeling & Pricing | `.exegol/unit_economics.json` |
| `product_poe` | Product Poe | Backlog Grooming & Prioritization | `.exegol/active_prompt.md` |
| `architect_artoo` | Architect Artoo | Architecture & Design Review | Architecture Diagrams/Docs |
| `research_rex` | Research Rex | Research & Web Intent | Backlog enrichment |
| `developer_dex` | Developer Dex | Implementation & Coding | Source Code & PRs |
| `quality_quigon` | Quality Qui-Gon | Testing, QA & Bug Logging | `.exegol/test_reports.json` |
| `markdown_mace` | Markdown Mace | Documentation & Formatting | Polished `.md` files |
| `evaluator_ezra` | Evaluator Ezra | Evaluation Research & Standards | Implementation requirements |
| `vibe_vader` | Vibe Vader | Identifies Imperial Human Actions | `.exegol/backlog.json` |
| `optimizer_ahsoka` | Optimizer Ahsoka | System Performance Optimization | Refined agent instructions |
| `report_revan` | Report Revan | Fleet Performance Reporting | Weekly Email/Slack summaries |
| `chief_of_staff_chewie` | Chief of Staff Chewie | Agent Performance Reviews | Performance Scorecards |
| `intel_ima` | Intel Ima | Intel & Cost Management | Cost/Cloud status reports |
| `assessment_anakin` | Assessment Anakin | Risk & Impact Assessment | `.exegol/assessment_report.json` |
| `compliance_cody` | Compliance Cody | Regulatory & Compliance Review | `.exegol/backlog.json` |
| `security_sabine` | Security Sabine | Security Hardening & Audits | Security Patches & PRs |
| `technical_tarkin` | Technical Tarkin | Technical Documentation & ADRs | Architecture decision records |
| `model_router_mothma` | Model Router Mothma | LLM Model Selection & Routing | Routing configuration |
| `watcher_wedge` | Watcher Wedge | System Health & Failure Monitoring | Backlog escalated items |
| `uat_ulic` | Uat Ulic | UAT Video Recording | WebM Video Previews |

## 🏗️ Technical Architecture

### FileSystem as State — A Novel Approach

> [!NOTE]
> Most AI agent systems break down at scale because they share state through fragile in-memory channels, huge context windows, or message queues that require complex orchestration. Exegol eliminates this entirely.

Exegol agents are **radically stateless**. There is no shared database, no message bus, no orchestration server. Every bit of coordination happens through structured files in the `.exegol/` directory:

| File | Purpose |
| :--- | :--- |
| `.exegol/backlog.json` | Master task registry — the single source of truth for all pending work |
| `.exegol/active_prompt.md` | The live instruction set for whichever agent is currently executing |
| `.exegol/roadmap.md` | Strategic planning context consumed by Product Poe and Architect Artoo |
| `interaction_logs/` | Immutable history for oversight agents (Ahsoka, Chewie, Revan) to analyze |

This design means any agent can be **killed and restarted at any time** without data loss. The fleet is inherently resilient, horizontally scalable, and completely debuggable — just `cat` a file to understand the full system state.

### Priority-Based Orchestration

The `ExegolOrchestrator` runs a continuous **Fleet Cycle**, making intelligent dispatch decisions in real-time:

1. 🔍 **Evaluate** — Reads `config/priority.json` to rank active repositories by urgency.
2. 📂 **Inspect** — Checks the `.exegol/` state for each active repo to determine what's needed.
3. ⚡ **Wake** — Dispatches the most appropriate specialist agent for the current context.
4. 🛠️ **Execute** — Runs the agent in a fully context-isolated session with enforced `max_step` limits.
5. 📊 **Status Update** — Captures the outcome and updates the repo state (Idle / Active / Blocked).

Blocked tasks automatically trigger a Slack notification for HITL escalation, preventing runaway loops.

---

## 🚀 Getting Started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your environment
cp .env.example .env  # Add your API keys

# 3. Launch the fleet
python src/orchestrator.py --fleet

# 🚀 Launch the Workbench (One-Click)
# This starts the API, the UI, and opens your browser automatically.
.\Start_Exegol.bat
```

Or, if you already know what you want: just say **`go`** and Exegol will identify the highest-priority repository and execute the predefined task suite for the appropriate agent — automatically.

---

## ✨ Why Exegol is Different

| Traditional AI Dev Tools | Exegol v3 |
| :--- | :--- |
| Single assistant, linear context | Fleet of 17+ specialized agents |
| Context window limits task scope | Stateless — unlimited task history via filesystem |
| Manual handoffs between steps | Fully autonomous agent-to-agent handoffs |
| Works on one repo at a time | Priority-ranked multi-repo orchestration |
| Breaks if session is interrupted | Restarts from exact filesystem state, zero data loss |
| No quality gate | QualityQuigon enforces regression testing on every change |

---
*Built with ❤️ by Antigravity — The Exegol Architect.*

---

## 🔎 Deep Dive: Anatomy of an Autonomous Action

The snapshot below captures a live moment in the Exegol development loop. This isn't just a log; it's a window into how the fleet thinks and executes.

![Active Prompt Example](image.png)

### Key Observations

* **The Active Prompt in Motion**: This demonstrates `.exegol/active_prompt.md` in action. It serves as the ephemeral "working memory" for the fleet—dynamically generated, executed against, and then replaced.
* **The "Go" Command & Autonomous Pivoting**: When the user issues a `go` command, the system performs a strategic pivot. Instead of following a linear path, **Developer Dex** analyzed the backlog and autonomously shifted to the most logical next action. Were this running outside of the IDE autonomously, Dex would've received Poe's handoff. The 'go' command was an example of how the stateless system functions.
* **Seamless Handoffs by Poe**: This context was prepared by **Product Poe**, who manages the transition between planning and implementation, ensuring the executing agent has zero ambiguity.
* **Continuous State Replacement**: The updates (indicated by green/red diffs in the logs) show how the active prompt is continuously overwritten. Exegol doesn't accumulate "chat history"; it maintains a clean, updated state.
* **Radical Persona Divergence**: Note the specific style of the implementation. Each agent brings a radically different "vibe" and technical approach, moving away from generic AI responses toward specialized expertise.
* **Backlog Integrity**: This shows that only formal agent calls or the global `go` command can modify the `.exegol/backlog.json`. This strict governance ensures a perfect audit trail of every decision.
* **Abstraction to No-Code**: This entire mechanical process is the engine for a future **No-Code UI**. By abstracting these agent loops, we enable complex development through high-level intent rather than manual syntax.

---

## 📡 Fleet Telemetry & The Slack Awareness Engine

The Exegol fleet doesn't just build code; it continuously monitors its own health and code quality. The system is deeply integrated with **Slack**, which serves as the fleet's decentralized command center. This integration ensures that while the fleet operates autonomously, it remains transparent, accountable, and connected to human oversight through three primary pillars:

### 1. Real-Time Awareness & Logging
Slack acts as a living, searchable log of fleet operations. From scheduled scans by **Watcher Wedge** to individual agent handoffs, every significant event is broadcast to dedicated channels. This provides a high-fidelity "pulse" of the repository's health and the fleet's progress, allowing humans to stay informed without needing to dive into raw log files.

### 2. Proactive Error Routing & Auto-Healing
When an agent encounters a fatal error—such as **Chief of Staff Chewie** crashing due to missing API credentials (e.g., `Gmail token not found`)—the system doesn't fail silently. The orchestrator catches the crash, alerts the team via Slack with the exact session ID and error snippet, and instantly injects a critical bug report into the backlog. This turns a system failure into a planned task automatically.

### 3. Frictionless Human-In-The-Loop (HITL)
Slack is the bridge for tasks that require human judgment. When **Vibe Vader** identifies a strategic gap or an agent hits a logic block, the fleet triggers an HITL request. These requests are delivered via Slack with deep-link context, allowing humans to provide high-level direction that is immediately captured back into the `.exegol/` state.

### 4. Interaction Layer Sync (Unified HITL)
The Exegol fleet maintains a synchronized "Human Action Required" queue across three primary interaction surfaces:
*   **Vibe-Coding Chat**: Direct interaction with agents during active development sessions.
*   **Exegol Workbench UI**: A dedicated Next.js dashboard for visual queue management and fleet metrics.
*   **Slack Interactive Messages**: Real-time broadcasts of HITL tasks with actionable buttons for instant approval/rejection.

All three surfaces are powered by a shared `HITLManager` and a central JSON data contract, ensuring that an action taken on one surface is instantly reflected across all others.

> [!TIP]
> This self-monitoring loop ensures the fleet is always aware of both the code's health and its own operational state, automatically turning insights and errors into planned work without requiring manual human triage.

