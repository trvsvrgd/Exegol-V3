import os
import sys
import json

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from tools.metrics_manager import SuccessMetricsManager

def test_metrics():
    print("Testing Advanced Success Metrics...")
    manager = SuccessMetricsManager(os.getcwd())
    report = manager.calculate_metrics(days=30)
    
    print(f"Report Timestamp: {report['timestamp']}")
    print(f"Total Sessions: {report['fleet_aggregate']['total_sessions']}")
    print(f"Average Recall: {report['fleet_aggregate']['avg_recall']}")
    print(f"Average Precision: {report['fleet_aggregate']['avg_precision']}")
    print(f"Overall Drift: {report['fleet_aggregate']['overall_drift']}")
    
    print("\nAgent Breakdown:")
    for agent_id, stats in report['agent_breakdown'].items():
        print(f"- {agent_id}:")
        print(f"  Recall: {stats['recall']}")
        print(f"  Precision: {stats['precision']}")
        print(f"  Drift: {stats['drift']}")
        print(f"  Status: {stats['status']}")

if __name__ == "__main__":
    test_metrics()
