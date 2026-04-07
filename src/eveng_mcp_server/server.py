"""MCP server exposing EVE-NG network lab operations as tools.

This is the main server module.  It uses the ``mcp`` SDK's ``FastMCP`` to
register tools that wrap the :class:`EveNGClient` async HTTP client.

Environment variables (all optional — defaults match the EVE-NG community
edition out of the box):

    EVENG_HOST      Base URL of the EVE-NG server (default ``http://192.168.122.10``)
    EVENG_USERNAME  API username (default ``admin``)
    EVENG_PASSWORD  API password (default ``eve``)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import EveNGClient, EveNGClientError
from .models import AddNodeInput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "eveng-mcp-server",
    instructions=(
        "MCP server providing AI agents with programmatic access to EVE-NG "
        "network labs.  Create, configure, and manage virtual network topologies."
    ),
)

# ---------------------------------------------------------------------------
# Shared client (lazy-initialised on first tool call)
# ---------------------------------------------------------------------------

_client: EveNGClient | None = None


def _get_client() -> EveNGClient:
    """Return (and optionally create) the shared EVE-NG client."""
    global _client
    if _client is None:
        _client = EveNGClient(
            base_url=os.environ.get("EVENG_HOST", "http://192.168.122.10"),
            username=os.environ.get("EVENG_USERNAME", "admin"),
            password=os.environ.get("EVENG_PASSWORD", "eve"),
        )
    return _client


def _fmt(data: Any) -> str:
    """Format API response data as a readable JSON string."""
    if isinstance(data, str):
        return data
    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tools — Lab Management
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_labs",
    description=(
        "List all labs on the EVE-NG server. "
        "Returns lab names, filenames, and paths. "
        "Optionally specify a folder path to list labs in a subfolder."
    ),
)
async def list_labs(folder: str = "/") -> str:
    """List all labs in a folder on the EVE-NG server.

    Args:
        folder: Folder path to list (default ``/`` for root).
    """
    client = _get_client()
    try:
        labs = await client.list_labs(folder)
        if not labs:
            return "No labs found."
        return _fmt(labs)
    except EveNGClientError as exc:
        return f"Error listing labs: {exc}"


@mcp.tool(
    name="get_lab",
    description=(
        "Get detailed information about a lab including its nodes, networks, "
        "and topology.  Returns lab metadata, all nodes with their status, "
        "and all networks."
    ),
)
async def get_lab(lab_path: str) -> str:
    """Get full details of a lab.

    Args:
        lab_path: Full lab path (e.g. ``/My Lab.unl`` or ``/folder/lab.unl``).
                  The ``.unl`` extension is added automatically if omitted.
    """
    client = _get_client()
    try:
        lab_info = await client.get_lab(lab_path)
        nodes = await client.list_nodes(lab_path)
        networks = await client.list_networks(lab_path)
        result = {
            "lab": lab_info,
            "nodes": nodes,
            "networks": networks,
        }
        return _fmt(result)
    except EveNGClientError as exc:
        return f"Error getting lab: {exc}"


@mcp.tool(
    name="create_lab",
    description=(
        "Create a new lab on the EVE-NG server. "
        "Specify a name, optional description, and folder path."
    ),
)
async def create_lab(
    name: str,
    description: str = "",
    path: str = "/",
    author: str = "",
    version: str = "1",
    body: str = "",
) -> str:
    """Create a new lab.

    Args:
        name: Lab name (becomes the filename, e.g. ``My Lab`` -> ``My Lab.unl``).
        description: Optional lab description.
        path: Folder where the lab is created (default ``/``).
        author: Optional author name.
        version: Lab version string (default ``1``).
        body: Optional lab notes/body text.
    """
    client = _get_client()
    try:
        result = await client.create_lab(
            name=name,
            path=path,
            description=description,
            version=version,
            author=author,
            body=body,
        )
        return f"Lab '{name}' created successfully.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error creating lab: {exc}"


@mcp.tool(
    name="delete_lab",
    description="Delete a lab from the EVE-NG server. This is irreversible.",
)
async def delete_lab(lab_path: str) -> str:
    """Delete a lab.

    Args:
        lab_path: Full lab path (e.g. ``/My Lab.unl``).
    """
    client = _get_client()
    try:
        result = await client.delete_lab(lab_path)
        return f"Lab '{lab_path}' deleted.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error deleting lab: {exc}"


# ---------------------------------------------------------------------------
# Tools — Images / Templates
# ---------------------------------------------------------------------------


@mcp.tool(
    name="list_images",
    description=(
        "List all available QEMU/Docker node images (templates) installed "
        "on the EVE-NG server.  Returns template names and descriptions."
    ),
)
async def list_images() -> str:
    """List available node templates/images."""
    client = _get_client()
    try:
        templates = await client.list_node_templates()
        if not templates:
            return "No templates found."
        return _fmt(templates)
    except EveNGClientError as exc:
        return f"Error listing images: {exc}"


# ---------------------------------------------------------------------------
# Tools — Node Management
# ---------------------------------------------------------------------------


@mcp.tool(
    name="add_node",
    description=(
        "Add a node (virtual device) to a lab.  Specify the template "
        "(image name), name, RAM, CPU, and number of interfaces.  "
        "Use 'list_images' first to see available templates."
    ),
)
async def add_node(
    lab_path: str,
    template: str,
    name: str = "",
    node_type: str = "qemu",
    ram: int = 1024,
    cpu: int = 1,
    ethernet: int = 2,
    serial: int = 0,
    image: str = "",
    console: str = "telnet",
    left: int = 0,
    top: int = 0,
    config: str = "0",
    delay: int = 0,
) -> str:
    """Add a node to a lab.

    Args:
        lab_path: Full lab path (e.g. ``/My Lab.unl``).
        template: Node template name (e.g. ``veos``, ``vexos``, ``csr1000v``).
        name: Display name for the node (auto-generated if empty).
        node_type: Virtualisation type — ``qemu``, ``dynamips``, ``iol``, ``docker``.
        ram: RAM in MB (default 1024).
        cpu: Number of vCPUs (default 1).
        ethernet: Number of Ethernet interfaces (default 2).
        serial: Number of serial interfaces (default 0).
        image: Specific image version (uses template default if empty).
        console: Console type — ``telnet``, ``vnc``, ``rdp`` (default ``telnet``).
        left: Canvas X position for the node icon.
        top: Canvas Y position for the node icon.
        config: Startup config mode — ``0``=none, ``1``=exported.
        delay: Boot delay in seconds.
    """
    client = _get_client()
    node_input = AddNodeInput(
        lab_path=lab_path,
        template=template,
        name=name,
        node_type=node_type,
        ram=ram,
        cpu=cpu,
        ethernet=ethernet,
        serial=serial,
        image=image,
        console=console,
        left=left,
        top=top,
        config=config,
        delay=delay,
    )
    try:
        result = await client.add_node(lab_path, node_input)
        return f"Node added to lab.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error adding node: {exc}"


@mcp.tool(
    name="start_node",
    description="Start a single node in a lab.  The node must already exist.",
)
async def start_node(lab_path: str, node_id: int) -> str:
    """Start a node.

    Args:
        lab_path: Full lab path.
        node_id: Numeric node ID.
    """
    client = _get_client()
    try:
        result = await client.start_node(lab_path, node_id)
        return f"Node {node_id} started.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error starting node {node_id}: {exc}"


@mcp.tool(
    name="stop_node",
    description="Stop a single node in a lab.",
)
async def stop_node(lab_path: str, node_id: int) -> str:
    """Stop a node.

    Args:
        lab_path: Full lab path.
        node_id: Numeric node ID.
    """
    client = _get_client()
    try:
        result = await client.stop_node(lab_path, node_id)
        return f"Node {node_id} stopped.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error stopping node {node_id}: {exc}"


@mcp.tool(
    name="start_all",
    description="Start all nodes in a lab simultaneously.",
)
async def start_all(lab_path: str) -> str:
    """Start all nodes in a lab.

    Args:
        lab_path: Full lab path.
    """
    client = _get_client()
    try:
        result = await client.start_all_nodes(lab_path)
        return f"All nodes starting.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error starting all nodes: {exc}"


@mcp.tool(
    name="stop_all",
    description="Stop all nodes in a lab simultaneously.",
)
async def stop_all(lab_path: str) -> str:
    """Stop all nodes in a lab.

    Args:
        lab_path: Full lab path.
    """
    client = _get_client()
    try:
        result = await client.stop_all_nodes(lab_path)
        return f"All nodes stopped.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error stopping all nodes: {exc}"


@mcp.tool(
    name="get_node_status",
    description=(
        "Get the current status of a node — whether it is running, stopped, "
        "or building.  Also returns node details like RAM, CPU, template, and console URL."
    ),
)
async def get_node_status(lab_path: str, node_id: int) -> str:
    """Get node status and details.

    Args:
        lab_path: Full lab path.
        node_id: Numeric node ID.
    """
    client = _get_client()
    try:
        node = await client.get_node(lab_path, node_id)
        # Add human-readable status
        status_code = node.get("status", 0) if isinstance(node, dict) else 0
        status_map = {0: "stopped", 1: "building", 2: "running"}
        if isinstance(node, dict):
            node["status_text"] = status_map.get(int(status_code), f"unknown({status_code})")
        return _fmt(node)
    except EveNGClientError as exc:
        return f"Error getting node status: {exc}"


# ---------------------------------------------------------------------------
# Tools — Configuration
# ---------------------------------------------------------------------------


@mcp.tool(
    name="push_config",
    description=(
        "Push a startup configuration to a node.  The node should be stopped "
        "before pushing config.  The configuration is stored and applied on "
        "next boot."
    ),
)
async def push_config(lab_path: str, node_id: int, config: str) -> str:
    """Push startup configuration to a node.

    Args:
        lab_path: Full lab path.
        node_id: Numeric node ID.
        config: Full configuration text to push.
    """
    client = _get_client()
    try:
        result = await client.push_node_config(lab_path, node_id, config)
        return f"Configuration pushed to node {node_id}.\n{_fmt(result)}"
    except EveNGClientError as exc:
        return f"Error pushing config to node {node_id}: {exc}"


@mcp.tool(
    name="get_node_config",
    description="Get a node's current startup configuration text.",
)
async def get_node_config(lab_path: str, node_id: int) -> str:
    """Get a node's startup configuration.

    Args:
        lab_path: Full lab path.
        node_id: Numeric node ID.
    """
    client = _get_client()
    try:
        config = await client.get_node_config(lab_path, node_id)
        if not config:
            return f"Node {node_id} has no startup configuration."
        return config
    except EveNGClientError as exc:
        return f"Error getting config for node {node_id}: {exc}"


# ---------------------------------------------------------------------------
# Tools — Network Connectivity
# ---------------------------------------------------------------------------


@mcp.tool(
    name="connect_nodes",
    description=(
        "Connect two nodes by creating a network and attaching their "
        "interfaces to it.  Specify the node IDs and interface IDs to "
        "connect.  Use 'get_lab' first to see available nodes and their "
        "interface IDs."
    ),
)
async def connect_nodes(
    lab_path: str,
    node1_id: int,
    node1_interface: int,
    node2_id: int,
    node2_interface: int,
    network_name: str = "",
    network_type: str = "bridge",
) -> str:
    """Connect two node interfaces via a shared network.

    This creates a new network and connects both specified interfaces to it.

    Args:
        lab_path: Full lab path.
        node1_id: First node's numeric ID.
        node1_interface: First node's interface ID to connect.
        node2_id: Second node's numeric ID.
        node2_interface: Second node's interface ID to connect.
        network_name: Name for the network (auto-generated if empty).
        network_type: Network type — ``bridge``, ``ovs``, ``pnet0``-``pnet9``.
    """
    client = _get_client()
    try:
        # Step 1: Create a network
        net_name = network_name or f"Net-{node1_id}-{node2_id}"
        net_result = await client.create_network(
            lab_path,
            name=net_name,
            network_type=network_type,
        )
        # Extract network ID from response
        # EVE-NG returns the new network ID in the response
        network_id = _extract_id(net_result)
        if network_id is None:
            return f"Error: could not determine network ID from response: {_fmt(net_result)}"

        # Step 2: Connect node1's interface to the network
        await client.connect_interface(lab_path, node1_id, node1_interface, network_id)

        # Step 3: Connect node2's interface to the network
        await client.connect_interface(lab_path, node2_id, node2_interface, network_id)

        return (
            f"Connected node {node1_id} (interface {node1_interface}) to "
            f"node {node2_id} (interface {node2_interface}) via network "
            f"'{net_name}' (id={network_id})."
        )
    except EveNGClientError as exc:
        return f"Error connecting nodes: {exc}"


def _extract_id(api_response: Any) -> int | None:
    """Extract a numeric ID from an EVE-NG create response.

    EVE-NG returns the new entity's ID in various formats depending
    on version — sometimes as ``{"id": 1}``, sometimes embedded in
    a URL string, sometimes as the raw integer.
    """
    if isinstance(api_response, int):
        return api_response
    if isinstance(api_response, dict):
        # Direct ID field
        if "id" in api_response:
            return int(api_response["id"])
        # Sometimes nested in data
        if "data" in api_response and isinstance(api_response["data"], dict):
            if "id" in api_response["data"]:
                return int(api_response["data"]["id"])
    if isinstance(api_response, str):
        # Try to parse as integer
        try:
            return int(api_response)
        except ValueError:
            pass
    return None
