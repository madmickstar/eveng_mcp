"""Pydantic models for EVE-NG API entities."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Enums ---


class NodeStatus(str, Enum):
    """Node runtime status as reported by EVE-NG."""

    STOPPED = "0"
    RUNNING = "2"
    # EVE-NG sometimes uses integer strings for status
    # 0 = stopped, 2 = running, 1 = building (rare)
    BUILDING = "1"


class NodeType(str, Enum):
    """Node virtualisation type."""

    QEMU = "qemu"
    DYNAMIPS = "dynamips"
    IOL = "iol"
    DOCKER = "docker"


# --- Authentication ---


class AuthRequest(BaseModel):
    """Login request body."""

    username: str = "admin"
    password: str = "eve"
    html5: int = Field(default=-1, description="Set to -1 for API-only access (no HTML5 console)")


class AuthResponse(BaseModel):
    """Parsed authentication response."""

    code: int
    message: str
    status: str


# --- Images ---


class NodeTemplate(BaseModel):
    """An available node image/template on the EVE-NG server."""

    name: str = Field(description="Template identifier (e.g. 'veos', 'vexos')")
    display_name: str = Field(default="", alias="description", description="Human-readable name")
    node_type: str = Field(default="qemu", alias="type")

    model_config = {"populate_by_name": True}


# --- Networks ---


class Network(BaseModel):
    """A network (bridge/cloud) inside a lab."""

    id: int = Field(description="Network numeric ID")
    name: str = Field(default="")
    network_type: str = Field(default="bridge1", alias="type")
    visibility: int = Field(default=1, description="1 = visible, 0 = hidden")
    left: int = Field(default=0, description="Canvas X position")
    top: int = Field(default=0, description="Canvas Y position")

    model_config = {"populate_by_name": True}


# --- Interfaces ---


class Interface(BaseModel):
    """A network interface on a node."""

    id: int = Field(description="Interface numeric ID")
    name: str = Field(default="")
    network_id: int = Field(default=0, description="ID of connected network (0 = disconnected)")

    model_config = {"populate_by_name": True}


# --- Nodes ---


class Node(BaseModel):
    """A node (virtual device) inside a lab."""

    id: int = Field(description="Node numeric ID")
    name: str = Field(default="")
    template: str = Field(default="", description="Template/image name")
    node_type: str = Field(default="qemu", alias="type")
    status: int = Field(default=0, description="0=stopped, 2=running")
    ram: int = Field(default=1024, description="RAM in MB")
    cpu: int = Field(default=1, description="vCPU count")
    image: str = Field(default="", description="Specific image version")
    console: str = Field(default="telnet", description="Console type (telnet, vnc, etc.)")
    ethernet: int = Field(default=2, description="Number of Ethernet interfaces")
    serial: int = Field(default=0, description="Number of serial interfaces")
    url: str = Field(default="", description="Console access URL")
    left: int = Field(default=0, description="Canvas X position")
    top: int = Field(default=0, description="Canvas Y position")
    config: str = Field(default="0", description="Startup config mode")
    delay: int = Field(default=0, description="Boot delay in seconds")

    model_config = {"populate_by_name": True}

    @property
    def is_running(self) -> bool:
        """Check if the node is currently running."""
        return self.status == 2


# --- Lab ---


class Lab(BaseModel):
    """A lab (topology file) on the EVE-NG server."""

    name: str = Field(default="", description="Lab display name")
    filename: str = Field(default="", description="Lab filename on disk (e.g. 'mylab.unl')")
    path: str = Field(default="", description="Full path including folders")
    description: str = Field(default="")
    author: str = Field(default="")
    version: str = Field(default="1")
    body: str = Field(default="", description="Lab notes/body text")

    model_config = {"populate_by_name": True}


class LabTopology(BaseModel):
    """Full lab topology including nodes and networks."""

    lab: Lab
    nodes: dict[int, Node] = Field(default_factory=dict)
    networks: dict[int, Network] = Field(default_factory=dict)


# --- API Response Wrapper ---


class EveApiResponse(BaseModel):
    """Generic EVE-NG API response wrapper."""

    code: int = Field(description="HTTP-like status code from EVE-NG")
    data: Any = Field(default=None, description="Response payload (varies by endpoint)")
    message: str = Field(default="")
    status: str = Field(default="success")


# --- Tool Input Models (used by MCP tool parameters) ---


class CreateLabInput(BaseModel):
    """Parameters for creating a new lab."""

    name: str = Field(description="Lab name (will be used as filename)")
    description: str = Field(default="", description="Lab description")
    author: str = Field(default="", description="Lab author name")
    version: str = Field(default="1", description="Lab version")
    body: str = Field(default="", description="Lab notes/body text")
    path: str = Field(
        default="/",
        description="Folder path on EVE-NG server where the lab will be created",
    )


class AddNodeInput(BaseModel):
    """Parameters for adding a node to a lab."""

    lab_path: str = Field(description="Lab path (e.g. '/My Lab.unl')")
    template: str = Field(description="Node template/image name (e.g. 'veos', 'vexos')")
    name: str = Field(default="", description="Node display name (auto-generated if empty)")
    node_type: str = Field(default="qemu", description="Virtualisation type: qemu, dynamips, iol, docker")
    ram: int = Field(default=1024, description="RAM in MB")
    cpu: int = Field(default=1, description="vCPU count")
    ethernet: int = Field(default=2, description="Number of Ethernet interfaces")
    serial: int = Field(default=0, description="Number of serial interfaces")
    image: str = Field(default="", description="Specific image version (optional, uses template default)")
    console: str = Field(default="telnet", description="Console type: telnet, vnc, rdp")
    left: int = Field(default=0, description="Canvas X position for visual layout")
    top: int = Field(default=0, description="Canvas Y position for visual layout")
    config: str = Field(default="0", description="Startup config: '0'=none, '1'=exported")
    delay: int = Field(default=0, description="Boot delay in seconds")


class ConnectNodesInput(BaseModel):
    """Parameters for connecting two node interfaces via a network."""

    lab_path: str = Field(description="Lab path (e.g. '/My Lab.unl')")
    network_name: str = Field(
        default="",
        description="Name for the connecting network (auto-generated if empty)",
    )
    network_type: str = Field(
        default="bridge",
        description="Network type: bridge, ovs, pnet0-pnet9",
    )
    node1_id: int = Field(description="First node ID")
    node1_interface: int = Field(description="First node interface ID")
    node2_id: int = Field(description="Second node ID")
    node2_interface: int = Field(description="Second node interface ID")
