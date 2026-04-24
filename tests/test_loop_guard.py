import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from orchestrator import ExegolOrchestrator
from handoff import SessionResult

class TestLoopGuard(unittest.TestCase):
    def setUp(self):
        # Mock priority.json path to avoid modifying real config during tests
        self.priority_patcher = patch('orchestrator.PRIORITY_FILE_PATH', 'tests/mock_priority.json')
        self.mock_priority_path = self.priority_patcher.start()
        
        # Create a dummy mock_priority.json
        with open('tests/mock_priority.json', 'w') as f:
            f.write('{"repositories": [{"repo_path": "test_repo", "priority": 1}], "global_settings": {"context_isolation": {"max_handoff_depth": 5}}}')
            
        self.orchestrator = ExegolOrchestrator()
        self.repo_info = {
            "repo_path": "test_repo",
            "priority": 1
        }
        
        # Mock Slack to avoid egress filter blocks
        self.slack_patcher = patch('orchestrator.slack_manager.post_message')
        self.slack_patcher.start()

    def tearDown(self):
        self.slack_patcher.stop()
        self.priority_patcher.stop()
        if os.path.exists('tests/mock_priority.json'):
            os.remove('tests/mock_priority.json')

    @patch('orchestrator.SessionManager.spawn_agent_session')
    def test_max_loop_depth_guard(self, mock_spawn):
        # Setup mock to request a sequence of different agents
        agents = ["product_poe", "developer_dex", "quality_quigon", "architect_artoo"]
        def side_effect(agent_id, module_path, class_name, handoff):
            depth = handoff.loop_depth
            # Use next agent in the list to avoid circuit breaker
            next_agent = agents[depth + 1] if depth + 1 < len(agents) else "intel_ima"
            return SessionResult(
                agent_id=agent_id,
                session_id=handoff.session_id,
                outcome="success",
                next_agent_id=next_agent
            )
        mock_spawn.side_effect = side_effect
        
        # Set max depth to 3
        self.orchestrator.priority_config["global_settings"]["context_isolation"]["max_handoff_depth"] = 3
        
        # Execute
        with patch.object(self.orchestrator, 'update_repo_status') as mock_status:
            self.orchestrator.wake_and_execute_agent(
                self.repo_info, "ollama", 10, agent_id="product_poe"
            )
            
            # depth 0: product_poe. CALL. next=developer_dex (depth 1)
            # depth 1: developer_dex. CALL. next=quality_quigon (depth 2)
            # depth 2: quality_quigon. CALL. next=architect_artoo (depth 3)
            # depth 3: architect_artoo. BLOCK.
            
            self.assertEqual(mock_spawn.call_count, 3)
            mock_status.assert_called_with("test_repo", "blocked")

    @patch('orchestrator.SessionManager.spawn_agent_session')
    def test_circuit_breaker_cycle_detection(self, mock_spawn):
        # Setup mock to cycle between poe and dex
        def side_effect(agent_id, module_path, class_name, handoff):
            next_agent = "developer_dex" if agent_id == "product_poe" else "product_poe"
            return SessionResult(
                agent_id=agent_id,
                session_id=handoff.session_id,
                outcome="success",
                next_agent_id=next_agent
            )
        
        mock_spawn.side_effect = side_effect
        
        # Execute
        with patch.object(self.orchestrator, 'update_repo_status') as mock_status:
            self.orchestrator.wake_and_execute_agent(
                self.repo_info, "ollama", 10, agent_id="product_poe"
            )
            
            # Chain:
            # 1. poe (depth 0, hist []) -> spawn(poe) -> next=dex
            # 2. dex (depth 1, hist [poe]) -> spawn(dex) -> next=poe
            # 3. poe (depth 2, hist [poe, dex]) -> count(poe)=1 (ok) -> spawn(poe) -> next=dex
            # 4. dex (depth 3, hist [poe, dex, poe]) -> count(dex)=1 (ok) -> spawn(dex) -> next=poe
            # 5. poe (depth 4, hist [poe, dex, poe, dex]) -> count(poe)=2 (BLOCK)
            
            self.assertEqual(mock_spawn.call_count, 4)
            mock_status.assert_called_with("test_repo", "blocked")

if __name__ == '__main__':
    unittest.main()
