import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.web_search import web_search
from tools.file_editor_tool import write_file

class SavantSifoAgent:
    """Researches the best models for given tasks, providing free/local and paid options."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "SavantSifoAgent"
        self.max_steps = 15
        self._steps_used = 0
        self.tools = ["web_search", "file_editor"]
        self.success_metrics = {
            "categories_researched": {
                "description": "Number of model categories researched and updated",
                "target": ">=5",
                "current": None
            },
            "research_freshness": {
                "description": "Days since the last model landscape scan",
                "target": "<=7",
                "current": None
            }
        }
        self.system_prompt = """
You are Savant Sifo, the Fleet's Model Strategist. Your mission is to research and recommend the absolute best LLMs and generative models for specific operational tasks. 

Your Core Directives:
1. Research and Identify: For a given task or set of categories, find the top-performing models currently available.
2. Dual Recommendations: For every category, you MUST provide two options:
   - Paid/API: High-performance, proprietary models (e.g., GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro).
   - Free/Local: High-efficiency, open-weights models that can run locally (e.g., Llama 3, Mistral, Gemma 2) or via free tiers.
3. Categories to Cover: Writing, Coding, Web Research, Image Generation, General Purpose, Audio/Voice, Video Generation.
4. Detailed Rationale: Explain WHY each model was chosen, considering factors like context window, reasoning capability, speed, and cost-effectiveness.

Output Format:
You must save your research report to `.exegol/research_reports/model_recommendations.json` and a human-readable version to `.exegol/research_reports/model_recommendations.md`.
"""

    def execute(self, handoff):
        """Execute the model research cycle."""
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — Starting model research cycle.")

        categories = ["Writing", "Coding", "Web Research", "Image Generation", "General Purpose", "Audio/Voice", "Video Generation"]
        
        try:
            # 1. Perform Research for each category
            report_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "categories": {}
            }
            
            for category in categories:
                if self._steps_used >= self.max_steps:
                    print(f"[{self.name}] Max steps reached. Finishing research with current results.")
                    break
                    
                print(f"[{self.name}] Researching category: {category}...")
                
                # Formulate search query
                query = f"best AI models for {category} 2024 2025 free local vs paid"
                search_results = web_search(query, num_results=5)
                self._steps_used += 1
                
                # Use LLM to process results and pick top 2
                analysis_prompt = f"Research category: {category}\nSearch Results: {json.dumps(search_results)}\n\nBased on these results, identify the best Paid/API model and the best Free/Local model for {category}. Provide: 1. Model Name (Paid), 2. Rationale (Paid), 3. Model Name (Free/Local), 4. Rationale (Free/Local). Return the result as a JSON object with keys: 'paid_name', 'paid_rationale', 'free_name', 'free_rationale'."
                
                analysis_response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
                analysis_data = self.llm_client.parse_json_response(analysis_response)
                self._steps_used += 1
                
                if analysis_data and "paid_name" in analysis_data:
                    report_data["categories"][category] = analysis_data
                else:
                    print(f"[{self.name}] Failed to analyze results for {category}")

            # 2. Save Reports
            reports_dir = os.path.join(repo_path, ".exegol", "research_reports")
            os.makedirs(reports_dir, exist_ok=True)
            
            json_report_path = os.path.join(reports_dir, "model_recommendations.json")
            with open(json_report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=4)
            
            md_report_path = os.path.join(reports_dir, "model_recommendations.md")
            md_content = self._generate_md_report(report_data)
            write_file(md_report_path, md_content)
            
            self._steps_used += 1
            
            duration = time.time() - start_time
            res = f"Model research completed for {len(report_data['categories'])} categories. Reports saved to {reports_dir}."
            
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                session_id=handoff.session_id
            )
            
            return res

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Model research failed: {str(e)}",
                repo_path=repo_path,
                steps_used=self._steps_used,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error during research: {e}"

    def _generate_md_report(self, data):
        md = f"# AI Model Recommendations Report\n\n"
        md += f"**Last Updated:** {data['timestamp']}\n\n"
        md += "This report summarizes the best AI models for various categories, providing both premium paid options and high-efficiency free/local alternatives.\n\n"
        
        for category, info in data["categories"].items():
            md += f"## {category}\n\n"
            md += f"### 💰 Paid / API Choice: **{info.get('paid_name', 'N/A')}**\n"
            md += f"{info.get('paid_rationale', 'No rationale provided.')}\n\n"
            md += f"### 🏠 Free / Local Choice: **{info.get('free_name', 'N/A')}**\n"
            md += f"{info.get('free_rationale', 'No rationale provided.')}\n\n"
            md += "---\n\n"
            
        md += "\n*Generated by Savant Sifo Agent*\n"
        return md
