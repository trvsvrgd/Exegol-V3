import os
import subprocess
import json
import psutil
from typing import Dict, Any

class HardwareScanner:
    """Detects local hardware capabilities (GPU VRAM, CPU, RAM) for inference optimization."""

    def __init__(self):
        self.gpu_info = self._detect_gpu()
        self.cpu_info = self._detect_cpu()
        self.ram_info = self._detect_ram()

    def scan(self) -> Dict[str, Any]:
        """Returns a full hardware profile."""
        return {
            "gpu": self.gpu_info,
            "cpu": self.cpu_info,
            "ram": self.ram_info,
            "os": os.name
        }

    def _detect_gpu(self) -> Dict[str, Any]:
        """Detects NVIDIA GPU details using nvidia-smi."""
        import shutil
        
        # Check if nvidia-smi is available in PATH
        nvsmi_path = shutil.which("nvidia-smi")
        
        # Fallback for common Windows path if not in global PATH
        if not nvsmi_path and os.name == 'nt':
            alt_path = r"C:\Windows\System32\nvidia-smi.exe"
            if os.path.exists(alt_path):
                nvsmi_path = alt_path

        if not nvsmi_path:
            return {"detected": False, "reason": "nvidia-smi binary not found in PATH or common locations."}

        try:
            # Run nvidia-smi with specific query format
            command = f"{nvsmi_path} --query-gpu=name,memory.total,memory.free,driver_version --format=csv,noheader,nounits"
            result = subprocess.run(
                [nvsmi_path, '--query-gpu=name,memory.total,memory.free,driver_version', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, check=True
            )
            
            # Always route terminal errors with 'FATAL' to the Exegol Fleet
            from tools.fatal_error_router import check_and_route_terminal_output
            check_and_route_terminal_output(os.getcwd(), result.stdout, result.stderr, command)
            
            lines = result.stdout.strip().split('\n')
            if not lines:
                return {"detected": False, "reason": "No GPU output from nvidia-smi"}
            
            # Assuming single GPU for now
            parts = [x.strip() for x in lines[0].split(',')]
            if len(parts) < 4:
                return {"detected": False, "reason": f"Malformed output from nvidia-smi: {lines[0]}"}
                
            name, total, free, driver = parts
            return {
                "detected": True,
                "name": name,
                "vram_total_mb": int(total),
                "vram_free_mb": int(free),
                "driver_version": driver
            }
        except Exception as e:
            error_msg = f"Error running nvidia-smi: {str(e)}"
            if "FATAL" in error_msg.upper():
                 from tools.fatal_error_router import route_fatal_error
                 route_fatal_error(os.getcwd(), error_msg)
            return {"detected": False, "reason": error_msg}

    def _detect_cpu(self) -> Dict[str, Any]:
        """Detects CPU details."""
        try:
            return {
                "count": psutil.cpu_count(logical=False),
                "logical_count": psutil.cpu_count(logical=True),
                "freq_mhz": psutil.cpu_freq().max if psutil.cpu_freq() else "unknown"
            }
        except:
            return {"count": "unknown"}

    def _detect_ram(self) -> Dict[str, Any]:
        """Detects System RAM details."""
        try:
            mem = psutil.virtual_memory()
            return {
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2)
            }
        except:
            return {"total_gb": "unknown"}

def get_hardware_profile() -> Dict[str, Any]:
    """Convenience function for quick hardware scanning."""
    scanner = HardwareScanner()
    return scanner.scan()

if __name__ == "__main__":
    print(json.dumps(get_hardware_profile(), indent=4))
