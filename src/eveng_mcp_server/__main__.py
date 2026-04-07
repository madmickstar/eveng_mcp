"""Entry point for the EVE-NG MCP Server.

Run directly with ``python -m eveng_mcp_server`` or via the installed
console script ``eveng-mcp-server``.

The server communicates over stdio using the MCP protocol.

Environment variables:
    EVENG_HOST      EVE-NG API base URL (default ``http://192.168.122.10``)
    EVENG_USERNAME  API username (default ``admin``)
    EVENG_PASSWORD  API password (default ``eve``)
"""

from __future__ import annotations

import logging
import sys


def main() -> None:
    """Start the EVE-NG MCP server on stdio."""
    # Configure logging to stderr so it doesn't interfere with MCP stdio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    logger = logging.getLogger("eveng_mcp_server")
    logger.info("Starting EVE-NG MCP Server")

    from .server import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
