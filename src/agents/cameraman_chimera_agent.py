class CameramanChimeraAgent:
    """Captures video walkthroughs of applications and embeds them into README files."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.name = "CameramanChimeraAgent"
        self.max_steps = 10
        self.tools = ["playwright_recorder", "video_clipper"]
        self.success_metrics = {
            "readme_video_coverage": {
                "description": "Percentage of repos with a README video loop or snippet",
                "target": "100%",
                "current": None
            },
            "video_generation_failures": {
                "description": "Number of failed video capture attempts per cycle",
                "target": "0",
                "current": None
            }
        }
        self.system_prompt = self.llm_client.generate_system_prompt(self)

    def execute(self, handoff):
        """Execute with a clean HandoffContext — no prior session memory required."""
        repo_path = handoff.repo_path
        print(f"[{self.name}] Session {handoff.session_id} — waking up for repo: {repo_path}")
        # Logic for Playwright goes here
        return "Success: Video captured and README updated."
