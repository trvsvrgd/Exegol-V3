import argparse
import os
import subprocess
import sys
from typing import Iterable, Set


def pids_for_ports(ports: Iterable[int]) -> Set[int]:
    wanted = {str(port) for port in ports}
    result = subprocess.run(
        ["netstat", "-aon"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    pids: Set[int] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        state = parts[-2]
        pid = parts[-1]
        if state.upper() != "LISTENING":
            continue
        if any(local_address.endswith(f":{port}") for port in wanted):
            try:
                pids.add(int(pid))
            except ValueError:
                continue
    return pids


def kill_pid(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            errors="replace",
        )
    else:
        result = subprocess.run(
            ["kill", "-TERM", str(pid)],
            capture_output=True,
            text=True,
            errors="replace",
        )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Release Exegol launcher ports.")
    parser.add_argument("--ports", nargs="+", type=int, default=[8000, 3000])
    args = parser.parse_args()

    pids = pids_for_ports(args.ports)
    if not pids:
        print(f"[ports] Already free: {', '.join(map(str, args.ports))}")
        return 0

    failed = []
    for pid in sorted(pids):
        if kill_pid(pid):
            print(f"[ports] Terminated PID {pid}")
        else:
            failed.append(pid)
            print(f"[ports] Failed to terminate PID {pid}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
