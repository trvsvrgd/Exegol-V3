import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.web_search import web_search
from tools.file_editor_tool import write_file
from tools.model_benchmark_db import (
    seed_if_empty, upsert_model, get_all_models,
    compare_models, recommend_for_role, get_ollama_models
)


# Maps agent roles to benchmark role keys
AGENT_ROLE_MAP = {
    "developer_dex": "coding",
    "architect_artoo": "coding",
    "quality_quigon": "coding",
    "product_poe": "writing",
    "report_revan": "writing",
    "chief_of_staff_chewie": "general",
    "thoughtful_thrawn": "research",
    "intel_ima": "research",
    "evaluator_ezra": "research",
    "research_rex": "research",
    "vibe_vader": "ops",
    "watcher_wedge": "ops",
    "optimizer_ahsoka": "ops",
    "security_sabine": "coding",
    "compliance_cody": "research",
    "technical_tarkin": "writing",
    "markdown_mace": "writing",
    "model_router_mothma": "research",
    "assessment_anakin": "general",
    "strategist_sloane": "general",
    "growth_galen": "research",
    "finance_fennec": "ops",
    "uat_ulic": "creative",
}


class ModelRouterMothmaAgent:
    """Evaluates and benchmarks LLMs across speed, coding, agentic ability, cost, and availability. Maintains a persistent benchmark database updated weekly via web research."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ModelRouterMothmaAgent"
        self.max_steps = 15
        self._steps_used = 0
        self.tools = ["web_search", "file_editor", "model_benchmark_db"]
        self.success_metrics = {
            "models_benchmarked": {
                "description": "Total models in benchmark database",
                "target": ">=20",
                "current": None
            },
            "research_freshness": {
                "description": "Days since the last model landscape scan",
                "target": "<=7",
                "current": None
            },
            "categories_covered": {
                "description": "Benchmark categories with data (coding, image, video, etc.)",
                "target": ">=5",
                "current": None
            }
        }
        self.system_prompt = """
You are Mothma, the Fleet Model Router. You maintain a benchmark database of AI models and help select the optimal model for every agent in the fleet.

Your Core Directives:
1. Weekly Research: Search the web for the latest model benchmarks, pricing, and Ollama availability.
2. Benchmark Database: Maintain scored entries (0-100) for each model across: coding, agentic, reasoning, speed, image_gen, video_gen, cost, multilingual.
3. Reference Comparisons: Always anchor unfamiliar models against well-known references (Claude Sonnet, Gemini Flash, GPT-5.5) so the user can calibrate.
4. Fleet Mapping: Assign the best model for each agent based on their role (coding, research, writing, ops, creative).
5. Dual Recommendations: For every role, recommend both a Paid/API option AND a Free/Local (Ollama) option.

Output: Return your findings as a JSON object with keys:
- "new_models": [{model_name, provider, scores...}] — any new or updated models
- "agent_mapping": {agent_id: recommended_model}
- "summary": brief text summary
"""

    def execute(self, handoff):
        """Execute the weekly model research and benchmarking cycle."""
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} Starting model benchmark cycle.")

        try:
            # Step 1: Ensure database is seeded
            model_count = seed_if_empty(repo_path)
            print(f"[{self.name}] Database has {model_count} models.")
            self._steps_used += 1

            # Step 2: Research new/updated models
            research_queries = [
                "best LLM models May 2026 benchmark coding agentic comparison",
                "new AI models released 2026 Ollama available performance",
                "AI model pricing comparison per token 2026 Claude Gemini GPT",
            ]

            all_search_results = []
            for query in research_queries:
                if self._steps_used >= self.max_steps:
                    break
                results = web_search(query, num_results=5)
                all_search_results.extend(results)
                self._steps_used += 1

            # Step 3: Ask LLM to extract new model data
            if all_search_results and self._steps_used < self.max_steps:
                existing = get_all_models(repo_path)
                existing_names = [m["model_name"] for m in existing]

                extraction_prompt = f"""Based on these search results, identify any NEW AI models or UPDATED benchmarks not already in our database.

Existing models: {json.dumps(existing_names)}

Search Results:
{json.dumps(all_search_results[:15], indent=2)}

For any new or significantly updated models, return a JSON object:
{{
  "new_models": [
    {{
      "model_name": "Example Model",
      "provider": "Provider Name",
      "tier": "frontier|mid|efficient",
      "category": "general|image|video",
      "coding_score": 0-100,
      "agentic_score": 0-100,
      "reasoning_score": 0-100,
      "speed_score": 0-100,
      "image_gen_score": 0-100,
      "video_gen_score": 0-100,
      "multilingual_score": 0-100,
      "cost_input_per_1m": float,
      "cost_output_per_1m": float,
      "cost_score": 0-100,
      "ollama_available": 0 or 1,
      "ollama_model_name": "name or empty",
      "context_window": int,
      "notes": "brief description"
    }}
  ],
  "summary": "what changed this week"
}}

If nothing new, return {{"new_models": [], "summary": "No new models detected"}}"""

                try:
                    response = self.llm_client.generate(
                        extraction_prompt,
                        system_instruction=self.system_prompt,
                        json_format=True
                    )
                    parsed = self.llm_client.parse_json_response(response)
                    self._steps_used += 1

                    # Upsert any new models
                    new_models = parsed.get("new_models", [])
                    for model_data in new_models:
                        if "model_name" in model_data and "provider" in model_data:
                            upsert_model(repo_path, model_data)
                            print(f"[{self.name}] Upserted: {model_data['model_name']}")
                except Exception as e:
                    print(f"[{self.name}] LLM extraction failed: {e}")

            # Step 4: Generate agent mapping
            agent_mapping = {}
            if self._steps_used < self.max_steps:
                for agent_id, role in AGENT_ROLE_MAP.items():
                    recs = recommend_for_role(repo_path, role)
                    if recs:
                        # Pick the top recommendation
                        best = recs[0]
                        agent_mapping[agent_id] = {
                            "recommended_model": best["model_name"],
                            "provider": best["provider"],
                            "weighted_score": best["weighted_score"],
                            "role": role,
                            "ollama_alternative": None
                        }
                        # Find best Ollama alternative
                        ollama_recs = [r for r in recs if r.get("ollama_available")]
                        if ollama_recs:
                            agent_mapping[agent_id]["ollama_alternative"] = ollama_recs[0]["model_name"]
                self._steps_used += 1

            # Step 5: Save reports
            all_models = get_all_models(repo_path)
            report = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_models": len(all_models),
                "agent_mapping": agent_mapping,
                "models": all_models
            }

            reports_dir = os.path.join(repo_path, ".exegol", "research_reports")
            os.makedirs(reports_dir, exist_ok=True)

            json_path = os.path.join(reports_dir, "model_benchmarks.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)

            md_path = os.path.join(reports_dir, "model_benchmarks.md")
            write_file(md_path, self._generate_md_report(report))
            self._steps_used += 1

            duration = time.time() - start_time
            res = f"Benchmark cycle complete. {len(all_models)} models tracked, {len(agent_mapping)} agents mapped."

            log_interaction(
                agent_id=self.name, outcome="success", task_summary=res,
                repo_path=repo_path, steps_used=self._steps_used,
                duration_seconds=duration, session_id=handoff.session_id
            )
            return res

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name, outcome="failure",
                task_summary=f"Benchmark cycle failed: {str(e)}",
                repo_path=repo_path, steps_used=self._steps_used,
                duration_seconds=duration, errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error: {e}"

    def _generate_md_report(self, data):
        md = "# 🤖 AI Model Benchmark Report\n\n"
        md += f"**Last Updated:** {data['timestamp']}  \n"
        md += f"**Total Models Tracked:** {data['total_models']}\n\n"

        md += "## Agent → Model Mapping\n\n"
        md += "| Agent | Role | Recommended | Ollama Alt |\n"
        md += "|-------|------|-------------|------------|\n"
        for agent, info in data.get("agent_mapping", {}).items():
            md += f"| {agent} | {info['role']} | {info['recommended_model']} | {info.get('ollama_alternative', 'N/A')} |\n"

        md += "\n## Model Benchmarks\n\n"
        md += "| Model | Provider | Coding | Agentic | Speed | Cost | Ollama |\n"
        md += "|-------|----------|--------|---------|-------|------|--------|\n"
        for m in data.get("models", []):
            ollama = "✅" if m.get("ollama_available") else "❌"
            md += f"| {m['model_name']} | {m['provider']} | {m['coding_score']} | {m['agentic_score']} | {m['speed_score']} | {m['cost_score']} | {ollama} |\n"

        md += "\n---\n*Generated by Model Router Mothma*\n"
        return md