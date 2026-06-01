import psutil
from fastapi import FastAPI
app = FastAPI()

@app.get("/metrics")
def get_metrics():
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_usage": psutil.virtual_memory().percent
    }