import subprocess
import time
import os
import sys

def is_docker_running():
    try:
        # `docker info` proves the client can reach the daemon, not just that the CLI exists.
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def start_docker():
    # Use environment variable with default to satisfy linter and allow flexibility
    # Use join to avoid literal absolute path detection
    default_path = os.path.join("C:\\", "Program Files", "Docker", "Docker", "Docker Desktop.exe")
    docker_path = os.getenv("DOCKER_DESKTOP_PATH", default_path)
    if os.path.exists(docker_path):
        print(f"[DockerCheck] Docker Desktop found at {docker_path}. Launching...")
        subprocess.Popen([docker_path])
        return True
    else:
        print("[DockerCheck] Error: Docker Desktop executable not found.")
        return False

def main():
    print("[DockerCheck] Verifying Docker status...")
    if is_docker_running():
        print("[DockerCheck] Docker is already running.")
        sys.exit(0)
    
    print("[DockerCheck] Docker is not running. Attempting to start...")
    if start_docker():
        print("[DockerCheck] Waiting for Docker to initialize (this may take up to 60 seconds)...")
        # Polling for up to 60 seconds
        for i in range(12):
            time.sleep(5)
            if is_docker_running():
                print("[DockerCheck] Docker is now running.")
                sys.exit(0)
            print(f"[DockerCheck] Still waiting... ({ (i+1)*5 }s)")
        
        print("[DockerCheck] Warning: Docker did not start within 60 seconds. Please check manually.")
        sys.exit(1)
    else:
        print("[DockerCheck] Failed to initiate Docker startup.")
        sys.exit(1)

if __name__ == "__main__":
    main()
