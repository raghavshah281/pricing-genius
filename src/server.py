"""Pricing Genius MCP Server.

Exposes competitor pricing intelligence via MCP tools.
Run locally: python src/server.py
"""

import os
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "Pricing Genius",
    instructions=(
        "Competitive pricing intelligence for ClickUp. "
        "Query pricing data for Smartsheet, Wrike, Asana, Notion, and Monday.com. "
        "Data is extracted daily from competitor pricing pages."
    ),
    # Disable DNS rebinding protection for Cloud Run (behind GCP's proxy)
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

# Register tools
from src.tools.query import register_query_tools

register_query_tools(mcp)

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        import uvicorn

        port = int(os.getenv("PORT", "8080"))
        app = mcp.streamable_http_app()
        uvicorn.run(app, host="0.0.0.0", port=port)
