import yaml
import os
from typing import Dict, Any

def generate_docker_compose(app_data: Dict[str, Any]) -> str:
    """
    Converts Exegol app.exegol.json data into a docker-compose.yml string.
    """
    app_name = app_data.get("app_name", "exegol_app")
    components = app_data.get("components", [])
    
    services = {}
    
    for comp in components:
        name = comp.get("name")
        image = comp.get("docker_image", f"{app_name}_{name}:latest")
        port = comp.get("port")
        
        service_config = {
            "image": image,
            "container_name": f"{app_name}_{name}",
            "restart": "always"
        }
        
        if port:
            service_config["ports"] = [f"{port}:{port}"]
            
        services[name] = service_config

    compose_data = {
        "version": "3.8",
        "services": services
    }
    
    return yaml.dump(compose_data, sort_keys=False)

def write_docker_compose(repo_path: str, content: str):
    """
    Writes the docker-compose.yml file to the repository root.
    """
    output_path = os.path.join(repo_path, "docker-compose.yml")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
