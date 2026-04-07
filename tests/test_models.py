"""Tests for Pydantic models."""

from __future__ import annotations

import pytest

from eveng_mcp_server.models import (
    AddNodeInput,
    AuthRequest,
    ConnectNodesInput,
    CreateLabInput,
    EveApiResponse,
    Interface,
    Lab,
    Network,
    Node,
    NodeStatus,
    NodeTemplate,
    NodeType,
)


# --- Enums ---


class TestNodeStatus:
    def test_status_values(self):
        assert NodeStatus.STOPPED == "0"
        assert NodeStatus.RUNNING == "2"
        assert NodeStatus.BUILDING == "1"

    def test_status_from_string(self):
        assert NodeStatus("0") == NodeStatus.STOPPED
        assert NodeStatus("2") == NodeStatus.RUNNING


class TestNodeType:
    def test_type_values(self):
        assert NodeType.QEMU == "qemu"
        assert NodeType.DOCKER == "docker"
        assert NodeType.DYNAMIPS == "dynamips"
        assert NodeType.IOL == "iol"


# --- AuthRequest ---


class TestAuthRequest:
    def test_defaults(self):
        req = AuthRequest()
        assert req.username == "admin"
        assert req.password == "eve"
        assert req.html5 == -1

    def test_custom_credentials(self):
        req = AuthRequest(username="user", password="pass123")
        assert req.username == "user"
        assert req.password == "pass123"


# --- NodeTemplate ---


class TestNodeTemplate:
    def test_from_api_response(self):
        data = {"name": "veos", "description": "Arista vEOS", "type": "qemu"}
        t = NodeTemplate(**data)
        assert t.name == "veos"
        assert t.display_name == "Arista vEOS"
        assert t.node_type == "qemu"

    def test_minimal(self):
        t = NodeTemplate(name="csr1000v")
        assert t.name == "csr1000v"
        assert t.display_name == ""
        assert t.node_type == "qemu"


# --- Network ---


class TestNetwork:
    def test_from_api_data(self):
        data = {"id": 1, "name": "Net-1", "type": "bridge", "visibility": 1}
        net = Network(**data)
        assert net.id == 1
        assert net.name == "Net-1"
        assert net.network_type == "bridge"
        assert net.visibility == 1

    def test_defaults(self):
        net = Network(id=5)
        assert net.name == ""
        assert net.network_type == "bridge1"
        assert net.visibility == 1
        assert net.left == 0
        assert net.top == 0


# --- Interface ---


class TestInterface:
    def test_connected(self):
        iface = Interface(id=0, name="e0", network_id=1)
        assert iface.network_id == 1

    def test_disconnected(self):
        iface = Interface(id=0, name="e0")
        assert iface.network_id == 0


# --- Node ---


class TestNode:
    def test_full_node(self):
        data = {
            "id": 1,
            "name": "R1",
            "template": "veos",
            "type": "qemu",
            "status": 2,
            "ram": 2048,
            "cpu": 2,
            "image": "veos-4.28",
            "ethernet": 4,
            "console": "telnet",
            "url": "telnet://192.168.1.1:32769",
        }
        node = Node(**data)
        assert node.id == 1
        assert node.name == "R1"
        assert node.template == "veos"
        assert node.node_type == "qemu"
        assert node.status == 2
        assert node.ram == 2048
        assert node.cpu == 2
        assert node.is_running is True

    def test_stopped_node(self):
        node = Node(id=2, name="R2", status=0)
        assert node.is_running is False

    def test_defaults(self):
        node = Node(id=1)
        assert node.name == ""
        assert node.ram == 1024
        assert node.cpu == 1
        assert node.ethernet == 2
        assert node.serial == 0
        assert node.console == "telnet"
        assert node.is_running is False


# --- Lab ---


class TestLab:
    def test_full_lab(self):
        lab = Lab(
            name="Test Lab",
            filename="Test Lab.unl",
            path="/Test Lab.unl",
            description="A test lab",
            author="Keith",
        )
        assert lab.name == "Test Lab"
        assert lab.filename == "Test Lab.unl"
        assert lab.description == "A test lab"

    def test_defaults(self):
        lab = Lab()
        assert lab.name == ""
        assert lab.version == "1"


# --- EveApiResponse ---


class TestEveApiResponse:
    def test_success_response(self):
        resp = EveApiResponse(code=200, data={"id": 1}, status="success", message="OK")
        assert resp.code == 200
        assert resp.data == {"id": 1}
        assert resp.status == "success"

    def test_error_response(self):
        resp = EveApiResponse(code=404, data=None, status="fail", message="Not found")
        assert resp.code == 404
        assert resp.data is None

    def test_data_can_be_any_type(self):
        resp = EveApiResponse(code=200, data=[1, 2, 3])
        assert resp.data == [1, 2, 3]

        resp2 = EveApiResponse(code=200, data="plain string")
        assert resp2.data == "plain string"


# --- CreateLabInput ---


class TestCreateLabInput:
    def test_required_fields(self):
        lab = CreateLabInput(name="My Lab")
        assert lab.name == "My Lab"
        assert lab.path == "/"
        assert lab.description == ""
        assert lab.version == "1"

    def test_all_fields(self):
        lab = CreateLabInput(
            name="VOSS Fabric",
            description="Multi-switch VOSS fabric",
            author="Keith",
            version="2",
            body="Production topology test",
            path="/networking/",
        )
        assert lab.name == "VOSS Fabric"
        assert lab.path == "/networking/"


# --- AddNodeInput ---


class TestAddNodeInput:
    def test_minimal(self):
        node = AddNodeInput(lab_path="/test.unl", template="veos")
        assert node.template == "veos"
        assert node.node_type == "qemu"
        assert node.ram == 1024
        assert node.cpu == 1
        assert node.ethernet == 2

    def test_full(self):
        node = AddNodeInput(
            lab_path="/test.unl",
            template="vexos",
            name="EXOS-1",
            ram=2048,
            cpu=2,
            ethernet=8,
            image="exos-32.1",
            console="vnc",
            left=100,
            top=200,
        )
        assert node.name == "EXOS-1"
        assert node.ram == 2048
        assert node.ethernet == 8
        assert node.console == "vnc"


# --- ConnectNodesInput ---


class TestConnectNodesInput:
    def test_required_fields(self):
        conn = ConnectNodesInput(
            lab_path="/test.unl",
            node1_id=1,
            node1_interface=0,
            node2_id=2,
            node2_interface=0,
        )
        assert conn.node1_id == 1
        assert conn.node2_id == 2
        assert conn.network_type == "bridge"
        assert conn.network_name == ""

    def test_with_network_name(self):
        conn = ConnectNodesInput(
            lab_path="/test.unl",
            node1_id=1,
            node1_interface=0,
            node2_id=2,
            node2_interface=1,
            network_name="backbone",
            network_type="ovs",
        )
        assert conn.network_name == "backbone"
        assert conn.network_type == "ovs"
