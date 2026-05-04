import os
import asyncio
import httpx
from mcp.server import Server
import mcp.types as types
from mcp.server.stdio import stdio_server

# Configuration
EXEGOL_API_URL = os.getenv("EXEGOL_API_URL", "http://localhost:8000")
EXEGOL_API_KEY = os.getenv("EXEGOL_API_KEY", "dev-local-key")

# Initialize MCP Server
app = Server("exegol-fleet")

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="route_fatal_error",
            description="Routes a terminal error with 'FATAL' status to the Exegol Fleet backlog.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Absolute path to the repository"},
                    "error_message": {"type": "string", "description": "The fatal error message or log snippet"},
                    "context": {"type": "string", "description": "Additional context or stack trace"}
                },
                "required": ["repo_path", "error_message"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "route_fatal_error":
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{EXEGOL_API_URL}/fatal-error",
                    json=arguments,
                    headers={"X-API-Key": EXEGOL_API_KEY},
                    timeout=10.0
                )
                response.raise_for_status()
                result = response.json()
                return [
                    types.TextContent(
                        type="text",
                        text=f"Successfully routed fatal error to Exegol Fleet. Task ID: {result.get('task_id')}"
                    )
                ]
            except Exception as e:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Failed to route error to Exegol Fleet: {str(e)}"
                    )
                ]
    
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
