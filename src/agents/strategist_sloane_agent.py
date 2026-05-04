import os
import json
import time
from tools.fleet_logger import log_interaction
from tools.web_search import web_search
from tools.diagram_generator import DiagramGenerator
from tools.backlog_manager import BacklogManager
from tools.metrics_manager import SuccessMetricsManager

class StrategistSloaneAgent:
    """Responsible for Market Intelligence & Horizontal Strategy.
    
    Reads business intent and generates a strategic brief including SWOT, competitive analysis,
    and proposed business models.
    """

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "StrategistSloaneAgent"
        self.max_steps = 10
        self.tools = ["web_search", "diagram_generator", "backlog_writer"]
        self.success_metrics = {
            "strategy_alignment_score": {
                "description": "User-rated alignment of the strategy brief with business goals",
                "target": ">=85%",
                "current": None
            },
            "market_research_depth": {
                "description": "Number of competitors identified and analyzed",
                "target": ">=5",
                "current": None
            }
        }
        self.system_prompt = """
You are Strategist Sloane, a top-tier business consultant and market intelligence expert within the Exegol v3 fleet.
Your core responsibility is 'Market Intelligence & Horizontal Strategy.'

Your Directives:
1. Identify Core Concept: Read .exegol/business_intent.json to understand the user's vision.
2. Market Intelligence: Perform web searches to analyze the competitive landscape and industry trends.
3. Strategic Synthesis: Generate a .exegol/strategy_brief.md containing:
   - SWOT Analysis (Strengths, Weaknesses, Opportunities, Threats)
   - Competitive Landscape (Detailed analysis of top competitors)
   - Three Proposed Business Models (e.g., SaaS, Marketplace, Agency) regardless of the domain.
4. Visual Strategy: Use the diagram_generator to visualize the proposed business architecture.
5. Handoff: Your output informs Product Poe's MVP feature definition.

Tone: Professional, authoritative, data-driven, and strategically forward-thinking.
"""
        self.metrics_manager = SuccessMetricsManager(os.getcwd())

    def execute(self, handoff):
        start_time = time.time()
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — Analyzing business strategy for repo: {repo_path}")

        exegol_dir = os.path.join(repo_path, ".exegol")
        os.makedirs(exegol_dir, exist_ok=True)
        intent_file = os.path.join(exegol_dir, "business_intent.json")
        brief_file = os.path.join(exegol_dir, "strategy_brief.md")

        try:
            # 1. Read Business Intent
            business_intent = {}
            if os.path.exists(intent_file):
                with open(intent_file, 'r', encoding='utf-8') as f:
                    business_intent = json.load(f)
            else:
                print(f"[{self.name}] business_intent.json not found. Using default context.")
                business_intent = {"intent": "Establish a new business entity based on current repository structure."}

            # 2. Market Research
            concept = business_intent.get("intent", "Unknown concept")
            print(f"[{self.name}] Researching market for: {concept}")
            search_results = web_search(f"market trends and competitors for: {concept}", num_results=5)

            # 3. Generate Strategy Brief
            prompt = f"""
            Analyze the following business intent and market research to generate a comprehensive Strategy Brief.
            
            Business Intent: {json.dumps(business_intent)}
            Market Research: {json.dumps(search_results)}
            
            Output a markdown file (.exegol/strategy_brief.md) that includes:
            - SWOT Analysis
            - Competitive Landscape
            - Three Proposed Business Models
            """
            
            strategy_brief = self.llm_client.generate(prompt, system_instruction=self.system_prompt)
            
            with open(brief_file, 'w', encoding='utf-8') as f:
                f.write(strategy_brief)

            # 4. Generate Business Architecture Diagram
            try:
                diagram = DiagramGenerator.generate_diagram(repo_path, self.llm_client)
                with open(os.path.join(exegol_dir, "business_architecture.mermaid"), 'w', encoding='utf-8') as f:
                    f.write(diagram)
            except Exception as e:
                print(f"[{self.name}] Diagram generation skipped: {e}")

            res = f"Strategy brief generated at {brief_file}. Handing off to product_poe."
            
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="success",
                task_summary=res,
                repo_path=repo_path,
                steps_used=2,
                duration_seconds=duration,
                session_id=handoff.session_id
            )
            return res

        except Exception as e:
            duration = time.time() - start_time
            log_interaction(
                agent_id=self.name,
                outcome="failure",
                task_summary=f"Strategy generation failed: {str(e)}",
                repo_path=repo_path,
                steps_used=1,
                duration_seconds=duration,
                errors=[str(e)],
                session_id=handoff.session_id
            )
            return f"[{self.name}] Error: {e}"
