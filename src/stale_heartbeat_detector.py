import time
from datetime import datetime, timedelta

class StaleHeartbeatDetector:
    def __init__(self, timeout_threshold=30):
        self.timeout_threshold = timeout_threshold

    def is_stale(self, last_heartbeat_time):
        current_time = datetime.now()
        return (current_time - last_heartbeat_time) > timedelta(seconds=self.timeout_threshold)