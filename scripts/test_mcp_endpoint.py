import requests

def test_fatal_error():
    url = "http://localhost:8000/fatal-error"
    headers = {"X-API-Key": "dev-local-key"}
    import os
    data = {
        "repo_path": os.getcwd(),
        "error_message": "FATAL: Database connection failed on startup",
        "context": "Traceback (most recent call last):\n  File \"api.py\", line 490, in <module>\n    uvicorn.run(app, host=\"0.0.0.0\", port=8000)"
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)  # nosec
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fatal_error()
