"""
KALISHI EDGE — Server Launcher
Ensures the local mcp/ package takes precedence over any installed mcp SDK.
Usage: python start.py
"""
import sys, os
# Keep local packages first so mcp/ isn't shadowed by installed mcp SDK
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
uvicorn.run(
    "mcp.server:app",
    host="0.0.0.0",
    port=8420,
    reload=False,
    log_level="info",
)
