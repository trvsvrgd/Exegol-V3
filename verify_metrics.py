import sys
import os
import json

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from tools.metrics_manager import SuccessMetricsManager

def verify_metrics():
    print("--- Verifying SuccessMetricsManager ---")
    repo_path = os.getcwd()
    manager = SuccessMetricsManager(repo_path)
    
    # Calculate metrics
    report = manager.calculate_metrics(days=7)
    
    print(f"Total Sessions analyzed: {report['fleet_aggregate']['total_sessions']}")
    print(f"Fleet Success Rate: {report['fleet_aggregate']['success_rate']*100:.1f}%")
    
    if report['agent_breakdown']:
        print("\nAgent Breakdown:")
        for agent, stats in report['agent_breakdown'].items():
            print(f" - {agent}: {stats['success_rate']*100:.1f}% success ({stats['total_sessions']} sessions)")
    else:
        print("\nNo interaction logs found for the last 7 days.")
    
    print("\nReport saved to .exegol/fleet_reports/metrics.json")

if __name__ == "__main__":
    verify_metrics()
