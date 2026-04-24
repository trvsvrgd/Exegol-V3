# Exegol v3 - Control Tower UI Recording Instructions

This document provides a step-by-step shot list and script for recording the **Exegol Control Tower UI**. The resulting video loop should be placed in the `README.md` to showcase the core functionality of the Exegol fleet to visitors on the front page of the repo.

## 🎥 Camera Settings & Prep
- **Resolution**: 1920x1080 (1080p).
- **Aspect Ratio**: 16:9.
- **Theme**: Ensure the app is loaded, fully populated with mock or real data (backlog, repos, queue items) to look busy and "alive."
- **Cursor**: Use a smooth cursor with a highlight effect for visibility during clicks.

---

## 🎬 Shot List & Actions

### **Shot 1: The Fleet Command Overview (0:00 - 0:05)**
**Purpose**: Show the bi-directional orchestrator landing page.
- **Action**: Start capturing the main `/` page. Slowly pan or just let the "Fleet Command" view sit for 2 seconds.
- **Focus**: The top-level repo cards with "Brain" models and "Status" (Active/Idle) glowing.
- **Interaction**: Mouse over 2-3 repo cards to show the subtle hover effects (`transform: translateY(-2px)` and glow). Finally, **click** on one of the active repository cards to select it.

### **Shot 2: Operational Intel & Backlog Triage (0:05 - 0:15)**
**Purpose**: Demonstrate task management and sprint grooming functionalities.
- **Action**: The view shifts down to the "Operational Intel" sector.
- **Interaction**:
  1. Click the **"Hide Completed"** checkbox toggle to show/hide done tasks.
  2. Click into the **Quick Add Task** input, type a brief example like *"Migrate HITL queue to new schema"*, and hit Enter. Verify it appears in the backlog.
  3. **Drag-and-Drop**: Click the `⋮⋮` drag handle on a medium-priority task, drag it to the top of the list, and drop it.
  4. Change a task's status via the dropdown from `TODO` to `IN PROGRESS`.

### **Shot 3: Human-In-The-Loop (Vibe Vader Queue) (0:15 - 0:22)**
**Purpose**: Highlight the asynchronous human intervention feature for the autonomous agent fleet.
- **Action**: Move the cursor over to the **"Vibe Vader Queue"** sidebar on the right.
- **Interaction**:
  1. Hover over a pending boundary-crossing item.
  2. Click inside the **notes textarea** and type a short directive (e.g., *"Approved, proceed with the destructive schema change."*).
  3. Click the custom **checkbox (`✓`)** to mark the item as resolved/done. 
  4. Quickly dismiss another item by clicking the `×` button.

### **Shot 4: Neural Distribution / Agent Settings (0:22 - 0:30)**
**Purpose**: Show how users can dynamically allocate LLM backends (local vs. cloud) to individual agents.
- **Action**: Click the **"Agent Settings"** button in the top right nav controls.
- **Interaction**:
  1. The UI transitions to the `/settings` page. Note the sleek fade-in animation.
  2. In the "Model Routing Matrix", click the dropdown for `ProductPoe`.
  3. Change it from `Ollama (Auto)` to a local specific model like `llama3` or to `Gemini 3 Pro (Cloud)`.
  4. Click the **"⚡ Save Allocation Config"** button at the bottom.
  5. Close the resulting sync confirmation alert.

---

## ✂️ Editing & Post-Production
- **Pacing**: Make sure each cut is smooth. Keep the actions brisk—no lingering.
- **Export format**: Export as a lightweight `.webm` or high-quality `.gif` / looping `.mp4`. 
- **Embed**: Embed directly into the primary `README.md` right after the main header:

> [!TIP]
> **Vibe Check for the UAT Agent**: The tone of the UI is "cybernetic/hacker" (glassmorphism, dark reds, glows). Ensure your demonstration feels precise and tactical.
