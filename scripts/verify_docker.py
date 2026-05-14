import subprocess
import time
import os
import sys

def is_docker_running():
    try:
        # Run docker version to check if the daemon is responsive
        result = subprocess.run(["docker", "version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False

def start_docker():
    docker_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if os.path.exists(docker_path):
        print(f"[DockerCheck] Docker Desktop found at {docker_path}. Launching...")
        # Use start to launch it detached
        subprocess.Popen([docker_path], shell=True)
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
