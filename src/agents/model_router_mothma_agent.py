import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.web_search import web_search
from tools.file_editor_tool import write_file

class ModelRouterMothmaAgent:
    """Evaluates and determines the best LLMs for specific tasks, providing Ollama-based and paid options."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "ModelRouterMothmaAgent"
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
You are Mothma, the Fleet Model Router. Your mission is to evaluate and determine the absolute best LLMs and generative models for each specific operational task, and map them to the active agents.

Your Core Directives:
1. Model Selection: For a given task or set of categories, identify the top-performing models currently available.
2. Dual Recommendations: For every category, you MUST provide two options:
   Paid/API: High-performance, proprietary models.
   Free/Local (Ollama): High-efficiency models that are specifically available through Ollama.
3. Categories to Cover: Writing, Coding, Web Research, Image Generation, General Purpose, Audio/Voice, Video Generation.
4. Task-Specific Rationale: Explain WHY each model was chosen for the task.
5. Fleet Mapping: You must assign the single best model (choosing the most appropriate from either paid or free) to each agent in the Exegol fleet based on their name and presumed role.

Output Format:
You must save your research report and agent mapping to .exegol/research_reports/model_recommendations.json and a human-readable version to .exegol/research_reports/model_recommendations.md.
"""

    def execute(self, handoff):
        """Execute the model research cycle."""
        start_time = time.time()
        self._steps_used = 0
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} Starting model research cycle.")

        categories = ["Writing", "Coding", "Web Research", "Image Generation", "General Purpose", "Audio/Voice", "Video Generation"]
        
        try:
            report_data = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "categories": {},
                "agent_mapping": {}
            }
            
            for category in categories:
                if self._steps_used >= self.max_steps:
                    print(f"[{self.name}] Max steps reached. Finishing research with current results.")
                    break
                    
                print(f"[{self.name}] Researching category: {category}...")
                
                query = f"best AI models for {category} 2024 2025 Ollama vs paid"
                search_results = web_search(query, num_results=5)
                self._steps_used += 1
                
                analysis_prompt = f"Research category: {category}\nSearch Results: {json.dumps(search_results)}\n\nBased on these results, identify the best Paid/API model and the best model available on Ollama for {category}. Provide: 1. Model Name (Paid), 2. Rationale (Paid), 3. Model Name (Ollama), 4. Rationale (Ollama). Return the result as a JSON object with keys: paid_name, paid_rationale, free_name, free_rationale."
                
                analysis_response = self.llm_client.generate(analysis_prompt, system_instruction=self.system_prompt, json_format=True)
                analysis_data = self.llm_client.parse_json_response(analysis_response)
                self._steps_used += 1
                
                if analysis_data and "paid_name" in analysis_data:
                    report_data["categories"][category] = analysis_data
                else:
                    print(f"[{self.name}] Failed to analyze results for {category}")

            agent_models_path = os.path.join(repo_path, "config", "agent_models.json")
            current_agents = {}
            if os.path.exists(agent_models_path):
                with open(agent_models_path, 'r', encoding='utf-8') as f:
                    current_agents = json.load(f)

            if current_agents and self._steps_used < self.max_steps:
                print(f"[{self.name}] Mapping models to agents...")
                agent_names = list(current_agents.keys())
                mapping_prompt = f"Here is the model research data you just compiled: {json.dumps(report_data['categories'])}\n\nHere are the agents currently in the fleet: {agent_names}.\n\nBased on their presumed roles (e.g., developer_dex is coding, product_poe is writing/general), assign the absolute best model choice (pick one from your paid or free findings) for each agent. Return a JSON object where the keys are the agent names and the values are the recommended model strings."
                
                mapping_response = self.llm_client.generate(mapping_prompt, system_instruction=self.system_prompt, json_format=True)
                mapping_data = self.llm_client.parse_json_response(mapping_response)
                self._steps_used += 1
                
                if mapping_data:
                    report_data["agent_mapping"] = mapping_data

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
            res = f"Model research completed for {len(report_data['categories'])} categories and mapped to {len(report_data.get('agent_mapping', {}))} agents. Reports saved to {reports_dir}."
            
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
        md += f"Last Updated: {data['timestamp']}\n\n"
        md += "This report summarizes the best AI models for various categories, and provides specific assignments for the fleet agents.\n\n"
        
        md += "## Agent Mapping Recommendations\n\n"
        if "agent_mapping" in data and data["agent_mapping"]:
            for agent, model in data["agent_mapping"].items():
                md += f"{agent}: {model}\n"
        else:
            md += "No agent mapping generated.\n"
        
        md += "\n## Category Research\n\n"
        for category, info in data["categories"].items():
            md += f"### {category}\n\n"
            md += f"Paid / API Choice: {info.get('paid_name', 'N/A')}\n"
            md += f"{info.get('paid_rationale', 'No rationale provided.')}\n\n"
            md += f"Ollama (Free/Local) Choice: {info.get('free_name', 'N/A')}\n"
            md += f"{info.get('free_rationale', 'No rationale provided.')}\n\n"
            md += "---\n\n"
            
        md += "\nGenerated by Model Router Mothma\n"
        return md