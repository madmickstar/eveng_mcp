# EVE-NG MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that gives Claude and other LLM agents programmatic access to [EVE-NG](https://www.eve-ng.net/) network labs.

Create, configure, and manage virtual network topologies through natural language — no manual clicking in the EVE-NG web UI required.

## Features

- **Lab management** — Create, list, get details, and delete labs
- **Node operations** — Add nodes from any installed template, start/stop individually or all at once
- **Configuration push** — Push startup configs to nodes before boot
- **Network connectivity** — Create networks and connect node interfaces
- **Image discovery** — List all available QEMU/Docker images on the server

## Requirements

- Python >= 3.10
- An EVE-NG server (Community or Professional) with API access
- An MCP-compatible client (Claude Desktop, Claude Code, etc.)

## Installation

```bash
# From source
git clone https://github.com/axiom-works-ai/eveng-mcp-server.git
cd eveng-mcp-server
pip install -e .

# With dev dependencies (for testing)
pip install -e ".[dev]"
```

## Configuration

The server reads connection details from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `EVENG_HOST` | `http://192.168.122.10` | EVE-NG API base URL |
| `EVENG_USERNAME` | `admin` | API username |
| `EVENG_PASSWORD` | `eve` | API password |

## Usage

### Claude Desktop

Add to your Claude Desktop MCP configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "eveng": {
      "command": "eveng-mcp-server",
      "env": {
        "EVENG_HOST": "http://192.168.122.10",
        "EVENG_USERNAME": "admin",
        "EVENG_PASSWORD": "eve"
      }
    }
  }
}
```

### Claude Code

Add to your Claude Code settings (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "eveng": {
      "command": "eveng-mcp-server",
      "env": {
        "EVENG_HOST": "http://192.168.122.10",
        "EVENG_USERNAME": "admin",
        "EVENG_PASSWORD": "eve"
      }
    }
  }
}
```

### Direct (stdio)

```bash
export EVENG_HOST=http://192.168.122.10
export EVENG_USERNAME=admin
export EVENG_PASSWORD=eve
eveng-mcp-server
```

Or run as a Python module:

```bash
python -m eveng_mcp_server
```

## Available Tools

### Lab Management

| Tool | Description |
|------|-------------|
| `list_labs` | List all labs on the server |
| `get_lab` | Get lab details with nodes, networks, and topology |
| `create_lab` | Create a new lab |
| `delete_lab` | Delete a lab |

### Node Operations

| Tool | Description |
|------|-------------|
| `add_node` | Add a node to a lab (specify template, RAM, CPU, interfaces) |
| `start_node` | Start a single node |
| `stop_node` | Stop a single node |
| `start_all` | Start all nodes in a lab |
| `stop_all` | Stop all nodes in a lab |
| `get_node_status` | Get node status and details |

### Configuration

| Tool | Description |
|------|-------------|
| `push_config` | Push startup configuration to a node |
| `get_node_config` | Get a node's current startup configuration |

### Network Connectivity

| Tool | Description |
|------|-------------|
| `connect_nodes` | Connect two node interfaces via a shared network |

### Discovery

| Tool | Description |
|------|-------------|
| `list_images` | List all installed QEMU/Docker images |

## Example Conversation

> **You:** Create a lab called "OSPF Demo" with two Arista vEOS switches connected together, then push basic OSPF configs to both.

The agent will:
1. Call `create_lab` to create "OSPF Demo"
2. Call `list_images` to find the vEOS template
3. Call `add_node` twice to add two vEOS switches
4. Call `connect_nodes` to link their interfaces
5. Call `push_config` on each node with OSPF configuration
6. Call `start_all` to boot the lab

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/ tests/
```

## EVE-NG API Notes

- The EVE-NG API uses **session cookies** (not bearer tokens) — the client authenticates once and reuses the session.
- Lab paths use URL-encoded filesystem paths (e.g., `/api/labs/My%20Lab.unl`).
- Node status codes: `0` = stopped, `1` = building, `2` = running.
- Startup configs should be pushed while the node is stopped.

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.

## Author

[Axiom Works AI](https://axiomworks.ai)
