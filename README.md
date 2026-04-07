# EVE-NG MCP Server

[![PyPI](https://img.shields.io/pypi/v/eveng-mcp-server)](https://pypi.org/project/eveng-mcp-server/)
[![CI](https://github.com/axiom-works-ai/eveng-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/axiom-works-ai/eveng-mcp-server/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/eveng-mcp-server)](https://pypi.org/project/eveng-mcp-server/)
[![License](https://img.shields.io/github/license/axiom-works-ai/eveng-mcp-server)](LICENSE)

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that gives Claude and other LLM agents programmatic access to [EVE-NG](https://www.eve-ng.net/) network labs.

Create, configure, and manage virtual network topologies through natural language — no manual clicking required.

```
You: "Create a lab with two Arista switches running OSPF, connected to each other"

Claude: ✓ Created lab "OSPF Demo"
        ✓ Added vEOS-1 (Arista vEOS 4.28)
        ✓ Added vEOS-2 (Arista vEOS 4.28)
        ✓ Connected e0/0 ↔ e0/0
        ✓ Pushed OSPF configs
        ✓ Started all nodes — lab is running
```

## Quick Start

### 1. Install

```bash
pip install eveng-mcp-server
```

### 2. Configure

Set your EVE-NG connection details:

```bash
export EVENG_HOST=http://your-eve-ng-server
export EVENG_USERNAME=admin
export EVENG_PASSWORD=eve
```

### 3. Add to Claude

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "eveng": {
      "command": "eveng-mcp-server",
      "env": {
        "EVENG_HOST": "http://your-eve-ng-server",
        "EVENG_USERNAME": "admin",
        "EVENG_PASSWORD": "eve"
      }
    }
  }
}
```

**Claude Code** — add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "eveng": {
      "command": "eveng-mcp-server",
      "env": {
        "EVENG_HOST": "http://your-eve-ng-server",
        "EVENG_USERNAME": "admin",
        "EVENG_PASSWORD": "eve"
      }
    }
  }
}
```

### 4. Use

Ask Claude to build you a network lab. That's it.

## How It Works

```
┌─────────────┐     MCP Protocol      ┌──────────────────┐     REST API     ┌─────────────┐
│   Claude /   │◄──────────────────────►│  EVE-NG MCP      │◄───────────────►│   EVE-NG    │
│   LLM Agent  │   (stdio transport)   │  Server           │  (HTTP + cookies)│   Server    │
└─────────────┘                        └──────────────────┘                  └─────────────┘
                                              │
                                       14 MCP Tools:
                                       create_lab, add_node,
                                       connect_nodes, push_config,
                                       start_all, etc.
```

The MCP server translates natural language requests from Claude into EVE-NG REST API calls. It handles authentication (session cookies), lab lifecycle, node management, configuration push, and network connectivity.

## Available Tools

### Lab Management

| Tool | Description |
|------|-------------|
| `list_labs` | List all labs on the server |
| `get_lab` | Get lab details — nodes, networks, links, status |
| `create_lab` | Create a new empty lab |
| `delete_lab` | Delete a lab and all its resources |

### Node Operations

| Tool | Description |
|------|-------------|
| `list_images` | Browse all installed QEMU and Docker images |
| `add_node` | Add a node to a lab — specify image, name, RAM, CPU, interface count |
| `start_node` | Start a single node |
| `stop_node` | Stop a single node |
| `start_all` | Start all nodes in a lab |
| `stop_all` | Stop all nodes in a lab |
| `get_node_status` | Get a node's current status and configuration |

### Configuration

| Tool | Description |
|------|-------------|
| `push_config` | Push startup configuration to a node (must be stopped) |
| `get_node_config` | Retrieve a node's current startup configuration |

### Networking

| Tool | Description |
|------|-------------|
| `connect_nodes` | Connect two node interfaces — creates a shared network and wires both endpoints |

## Usage Examples

### Build a Multi-Vendor Lab

> "Create a lab called 'Data Center Fabric' with 2 VOSS spine switches and 4 EXOS leaf switches. Connect each leaf to both spines."

Claude will use `list_images` to find your installed Extreme images, create the lab, add 6 nodes, and wire the spine-leaf fabric.

### Push Configs Before Boot

> "Push OSPF configuration to all routers in the lab, then start everything."

Claude will call `push_config` on each node with vendor-appropriate configuration, then `start_all` to boot the lab.

### Inspect Lab State

> "Show me what's running in the BGP lab — which nodes are up, which are still booting?"

Claude calls `get_lab` to retrieve the full topology with per-node status.

### Tear Down and Rebuild

> "Destroy the current lab and build a new one with 3 Cisco IOSv routers in a triangle topology."

Claude calls `delete_lab`, then `create_lab`, `add_node` x3, and `connect_nodes` x3.

## Common Use Cases

### Certification Lab Prep (CCNA/CCNP/CCIE)

> "Build me a lab for practicing OSPF multi-area with 5 routers — one ABR connecting area 0 and area 1, with stub and NSSA areas."

The MCP server handles the tedious setup: creating the lab, adding nodes, wiring interfaces, and pushing base configs so you can focus on the protocol practice.

### Pre-Change Validation

> "I need to test adding a new VLAN to our spine-leaf fabric before doing it in production. Build a lab that mirrors our 2-spine 4-leaf topology with VOSS switches."

Build a lab topology matching production, test your change, verify traffic flow — all through conversation with Claude.

### Vendor Comparison / PoC

> "Create two identical 3-router triangle topologies — one with Arista vEOS and one with Cisco IOSv. Push BGP configs to both so I can compare convergence behavior."

Side-by-side vendor comparison without manually building two separate labs.

### Training and Demos

> "Set up a classroom lab with 5 separate student topologies, each with 2 routers and 1 switch, all pre-configured with basic connectivity."

Quickly spin up multiple isolated lab instances for training sessions.

### Network Automation Development

> "Create a 4-router lab and start all nodes. I need to test my Ansible playbooks against real network devices."

Use the MCP server to provision labs for testing Ansible, Nornir, Terraform, or any network automation tooling.

### Troubleshooting Practice

> "Build a lab with intentional misconfigurations — wrong OSPF area IDs, mismatched BGP AS numbers, or broken VLAN trunks — and don't tell me what's wrong."

AI-generated fault injection for network troubleshooting practice.

## Prerequisites

- **Python 3.10+**
- **EVE-NG server** (Community or Professional) with API access enabled
  - The server must be reachable from where the MCP server runs
  - Default EVE-NG API port is 80 (HTTP) or 443 (HTTPS)
  - Default credentials: `admin` / `eve`
- **MCP-compatible client** — Claude Desktop, Claude Code, or any MCP client

### EVE-NG Network Access

The MCP server connects to EVE-NG's REST API over HTTP. Your EVE-NG server must be reachable:

| Setup | EVENG_HOST Value |
|-------|------------------|
| Same machine | `http://localhost` |
| Local network | `http://192.168.1.100` |
| Via Tailscale | `http://100.x.y.z:8080` |
| Via SSH tunnel | `http://localhost:8080` (after `ssh -L 8080:192.168.122.10:80 jump-host`) |

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `EVENG_HOST` | `http://192.168.122.10` | EVE-NG API base URL |
| `EVENG_USERNAME` | `admin` | API username |
| `EVENG_PASSWORD` | `eve` | API password |

## Troubleshooting

**"Connection refused" or timeout**
- Verify EVE-NG is running and the API is accessible: `curl http://your-server/api/status`
- Check firewall rules — EVE-NG API runs on port 80 by default
- If using a jump host, set up an SSH tunnel first

**"Authentication failed"**
- Default credentials are `admin` / `eve`
- EVE-NG Community Edition limits to 2 admin accounts
- Check if another session is active (EVE-NG allows one session per user)

**"Image not found" when adding nodes**
- Run `list_images` to see what's installed
- EVE-NG image folder names must follow exact naming conventions
- QEMU images go in `/opt/unetlab/addons/qemu/`

**Node starts but no console access**
- Nodes need 30-120 seconds to fully boot (vendor dependent)
- Use `get_node_status` to check if the node is still building (status=1) or running (status=2)

## Development

```bash
# Clone and install
git clone https://github.com/axiom-works-ai/eveng-mcp-server.git
cd eveng-mcp-server
pip install -e ".[dev]"

# Run tests (69 tests, mocked — no EVE-NG server needed)
pytest

# Run with verbose output
pytest -v

# Type check
mypy src/eveng_mcp_server/ --ignore-missing-imports
```

## EVE-NG API Notes

- Uses **session cookies** for authentication (not bearer tokens)
- Lab paths are URL-encoded filesystem paths (e.g., `/api/labs/My%20Lab.unl`)
- Node status codes: `0` = stopped, `1` = building/booting, `2` = running
- Push startup configs while nodes are **stopped** — they apply at next boot
- `connect_nodes` is a compound operation: creates a network, then attaches both interfaces

## License

[Apache-2.0](LICENSE)

## Author

Built by [Axiom Works AI](https://axiomworks.ai) — AI-powered tools for network engineers.
