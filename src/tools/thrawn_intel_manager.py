import os
import re
from typing import List, Dict, Any, Optional

class ThrawnIntelManager:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.exegol_dir = os.path.join(repo_path, ".exegol")
        self.intent_file = os.path.join(self.exegol_dir, "intent.md")
        self.roadmap_file = os.path.join(self.exegol_dir, "roadmap.md")

    def _validate_path(self, path: str):
        """Safeguard: Ensure we only modify human-interaction markdowns in .exegol/ or root README.md."""
        abs_path = os.path.abspath(path)
        abs_exegol = os.path.abspath(self.exegol_dir)
        abs_readme = os.path.abspath(os.path.join(self.repo_path, "README.md"))
        
        is_in_exegol = abs_path.startswith(abs_exegol) and abs_path.endswith(".md")
        is_root_readme = abs_path == abs_readme
        
        if not (is_in_exegol or is_root_readme):
            raise PermissionError(f"Thrawn is restricted from modifying non-interaction file: {path}")

    def read_intent(self) -> Dict[str, Any]:
        if not os.path.exists(self.intent_file):
            return {
                "objective": "",
                "architecture": [],
                "questions": []
            }

        with open(self.intent_file, 'r', encoding='utf-8') as f:
            content = f.read()

        intel = {
            "objective": "",
            "architecture": [],
            "questions": []
        }

        # Simple regex-based parsing
        objective_match = re.search(r"## 🎯 Primary Objective\s*\n(.*?)(?=\n##|$)", content, re.DOTALL)
        if objective_match:
            intel["objective"] = objective_match.group(1).strip()

        architecture_match = re.search(r"## 🏗️ Architecture & Patterns\s*\n(.*?)(?=\n##|$)", content, re.DOTALL)
        if architecture_match:
            arch_text = architecture_match.group(1).strip()
            intel["architecture"] = [line.strip("- ").strip() for line in arch_text.splitlines() if line.strip().startswith("-")]

        questions_match = re.search(r"## ❓ Open Clarification Questions.*?\s*\n(.*?)(?=\n##|$)", content, re.DOTALL)
        if questions_match:
            q_text = questions_match.group(1).strip()
            lines = q_text.splitlines()
            current_q = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Match "1. Question" or "- Question"
                q_match = re.match(r"^(\d+\.|\-)\s+(.*)", line)
                if q_match:
                    if current_q:
                        intel["questions"].append(current_q)
                    current_q = {"question": q_match.group(2).strip(), "answer": None}
                elif line.lower().startswith("answer:") and current_q:
                    current_q["answer"] = line[7:].strip()
                elif current_q:
                    # Append to question or answer if multi-line (simple approach)
                    if current_q["answer"] is not None:
                        current_q["answer"] += " " + line
                    else:
                        current_q["question"] += " " + line
            if current_q:
                intel["questions"].append(current_q)

        return intel

    def update_objective(self, objective: str):
        intel = self.read_intent()
        intel["objective"] = objective
        self.save_intent(intel)

    def add_architecture(self, pattern: str):
        intel = self.read_intent()
        intel["architecture"].append(pattern)
        self.save_intent(intel)

    def answer_question(self, question_text: str, answer: str):
        intel = self.read_intent()
        found = False
        for q in intel["questions"]:
            if q["question"] == question_text:
                q["answer"] = answer
                found = True
                break
        if not found:
            # Maybe it's a substring match or we just add it?
            # For now, let's just add it if not found exactly
            intel["questions"].append({"question": question_text, "answer": answer})
        self.save_intent(intel)

    def save_intent(self, intel: Dict[str, Any]):
        os.makedirs(os.path.dirname(self.intent_file), exist_ok=True)
        
        lines = [
            "# 🚀 Repository Intent & Clarifications",
            "",
            "## 🎯 Primary Objective",
            "",
            intel["objective"],
            "",
            "## 🏗️ Architecture & Patterns",
            ""
        ]
        
        for pattern in intel["architecture"]:
            lines.append(f"- {pattern}")
        
        lines.append("")
        lines.append("## ❓ Open Clarification Questions (Active Grooming)")
        lines.append("")
        
        for i, q in enumerate(intel["questions"], 1):
            lines.append(f"{i}. {q['question']}")
            if q["answer"]:
                lines.append(f"   Answer: {q['answer']}")
        
        with open(self.intent_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines) + "\n")

    def read_roadmap(self) -> str:
        if not os.path.exists(self.roadmap_file):
            return ""
        with open(self.roadmap_file, 'r', encoding='utf-8') as f:
            return f.read()

    def save_roadmap(self, content: str):
        self._validate_path(self.roadmap_file)
        os.makedirs(self.exegol_dir, exist_ok=True)
        with open(self.roadmap_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def add_roadmap_item(self, section: str, item: str):
        """Add a new item to a specific section in the roadmap."""
        content = self.read_roadmap()
        lines = content.splitlines()
        new_lines = []
        section_found = False
        
        for line in lines:
            new_lines.append(line)
            if section.lower() in line.lower() and (line.startswith("##") or line.startswith("###")):
                section_found = True
                new_lines.append(f"- [ ] {item}")
        
        if not section_found:
            # If section doesn't exist, append it at the end
            new_lines.append(f"\n## {section}")
            new_lines.append(f"- [ ] {item}")
            
        self.save_roadmap("\n".join(new_lines) + "\n")

    def redact_roadmap_item(self, pattern: str):
        """Redact a line from the roadmap matching the pattern."""
        content = self.read_roadmap()
        lines = content.splitlines()
        new_lines = [line for line in lines if pattern.lower() not in line.lower()]
        self.save_roadmap("\n".join(new_lines) + "\n")
