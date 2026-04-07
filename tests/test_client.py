"""Tests for the EVE-NG async HTTP client.

Uses ``respx`` to mock httpx requests so no real EVE-NG server is needed.
"""

from __future__ import annotations

import pytest
import respx
import httpx

from eveng_mcp_server.client import EveNGClient, EveNGClientError
from eveng_mcp_server.models import AddNodeInput


BASE_URL = "http://testhost"
API_URL = f"{BASE_URL}/api"


@pytest.fixture
def client():
    """Create an EveNGClient pointed at a test host."""
    return EveNGClient(base_url=BASE_URL, username="admin", password="eve")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    @respx.mock
    @pytest.mark.asyncio
    async def test_login_success(self, client):
        respx.post(f"{API_URL}/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success", "message": "User logged in"},
            )
        )
        result = await client.login()
        assert client._authenticated is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_failure(self, client):
        respx.post(f"{API_URL}/auth/login").mock(
            return_value=httpx.Response(
                401,
                json={"code": 401, "data": None, "status": "fail", "message": "Invalid credentials"},
            )
        )
        with pytest.raises(EveNGClientError) as exc_info:
            await client.login()
        assert "Invalid credentials" in str(exc_info.value)

    @respx.mock
    @pytest.mark.asyncio
    async def test_logout(self, client):
        # Login first
        respx.post(f"{API_URL}/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success", "message": "OK"},
            )
        )
        respx.get(f"{API_URL}/auth/logout").mock(
            return_value=httpx.Response(200, json={"code": 200, "status": "success"})
        )
        await client.login()
        assert client._authenticated is True
        await client.logout()
        assert client._authenticated is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_ensure_authenticated_calls_login(self, client):
        respx.post(f"{API_URL}/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success", "message": "OK"},
            )
        )
        assert client._authenticated is False
        await client.ensure_authenticated()
        assert client._authenticated is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_ensure_authenticated_skips_if_already_authed(self, client):
        client._authenticated = True
        # Should NOT make any HTTP calls
        await client.ensure_authenticated()
        assert client._authenticated is True


# ---------------------------------------------------------------------------
# Templates / Images
# ---------------------------------------------------------------------------


class TestTemplates:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_node_templates(self, client):
        client._authenticated = True
        templates = {
            "veos": {"name": "veos", "description": "Arista vEOS"},
            "csr1000v": {"name": "csr1000v", "description": "Cisco CSR1000v"},
        }
        respx.get(f"{API_URL}/list/templates/").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": templates, "status": "success"},
            )
        )
        result = await client.list_node_templates()
        assert "veos" in result
        assert "csr1000v" in result


# ---------------------------------------------------------------------------
# Labs
# ---------------------------------------------------------------------------


class TestLabs:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_labs(self, client):
        client._authenticated = True
        labs = {
            "lab1.unl": {"name": "Lab 1", "filename": "lab1.unl", "path": "/lab1.unl"},
            "lab2.unl": {"name": "Lab 2", "filename": "lab2.unl", "path": "/lab2.unl"},
        }
        respx.get(f"{API_URL}/folders/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {"folders": [], "labs": labs},
                    "status": "success",
                },
            )
        )
        result = await client.list_labs("/")
        assert len(result) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_labs_empty(self, client):
        client._authenticated = True
        respx.get(f"{API_URL}/folders/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {"folders": [], "labs": {}},
                    "status": "success",
                },
            )
        )
        result = await client.list_labs("/")
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_lab(self, client):
        client._authenticated = True
        lab_data = {"name": "Test", "filename": "Test.unl", "description": "A test lab"}
        respx.get(f"{API_URL}/labs/Test.unl").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": lab_data, "status": "success"},
            )
        )
        result = await client.get_lab("/Test.unl")
        assert result["name"] == "Test"

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_lab(self, client):
        client._authenticated = True
        respx.post(f"{API_URL}/labs").mock(
            return_value=httpx.Response(
                201,
                json={"code": 201, "data": {}, "status": "success", "message": "Lab created"},
            )
        )
        result = await client.create_lab(name="New Lab", description="Test")
        # Should not raise

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_lab(self, client):
        client._authenticated = True
        respx.delete(f"{API_URL}/labs/Test.unl").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success", "message": "Lab deleted"},
            )
        )
        result = await client.delete_lab("/Test.unl")


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


class TestNodes:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_nodes(self, client):
        client._authenticated = True
        nodes = {
            "1": {"id": 1, "name": "R1", "template": "veos", "status": 0},
            "2": {"id": 2, "name": "R2", "template": "veos", "status": 2},
        }
        respx.get(f"{API_URL}/labs/Test.unl/nodes").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": nodes, "status": "success"},
            )
        )
        result = await client.list_nodes("/Test.unl")
        assert "1" in result
        assert result["1"]["name"] == "R1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_node(self, client):
        client._authenticated = True
        node_data = {"id": 1, "name": "R1", "status": 2, "ram": 2048}
        respx.get(f"{API_URL}/labs/Test.unl/nodes/1").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": node_data, "status": "success"},
            )
        )
        result = await client.get_node("/Test.unl", 1)
        assert result["name"] == "R1"
        assert result["status"] == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_node(self, client):
        client._authenticated = True
        respx.post(f"{API_URL}/labs/Test.unl/nodes").mock(
            return_value=httpx.Response(
                201,
                json={"code": 201, "data": {"id": 3}, "status": "success", "message": "Node added"},
            )
        )
        node_input = AddNodeInput(lab_path="/Test.unl", template="veos", name="R3", ram=2048)
        result = await client.add_node("/Test.unl", node_input)
        assert result["id"] == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_node_no_name(self, client):
        """When name is empty, it should be excluded from the payload so EVE-NG auto-generates."""
        client._authenticated = True
        captured_request = {}

        def capture_request(request):
            import json as json_mod
            captured_request["body"] = json_mod.loads(request.content)
            return httpx.Response(
                201,
                json={"code": 201, "data": {"id": 1}, "status": "success"},
            )

        respx.post(f"{API_URL}/labs/Test.unl/nodes").mock(side_effect=capture_request)
        node_input = AddNodeInput(lab_path="/Test.unl", template="veos")
        await client.add_node("/Test.unl", node_input)
        assert "name" not in captured_request["body"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_start_node(self, client):
        client._authenticated = True
        respx.get(f"{API_URL}/labs/Test.unl/nodes/1/start").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success", "message": "Node started"},
            )
        )
        result = await client.start_node("/Test.unl", 1)

    @respx.mock
    @pytest.mark.asyncio
    async def test_stop_node(self, client):
        client._authenticated = True
        respx.get(f"{API_URL}/labs/Test.unl/nodes/1/stop").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success", "message": "Node stopped"},
            )
        )
        result = await client.stop_node("/Test.unl", 1)

    @respx.mock
    @pytest.mark.asyncio
    async def test_start_all_nodes(self, client):
        client._authenticated = True
        respx.get(f"{API_URL}/labs/Test.unl/nodes/start").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success"},
            )
        )
        await client.start_all_nodes("/Test.unl")

    @respx.mock
    @pytest.mark.asyncio
    async def test_stop_all_nodes(self, client):
        client._authenticated = True
        respx.get(f"{API_URL}/labs/Test.unl/nodes/stop").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success"},
            )
        )
        await client.stop_all_nodes("/Test.unl")

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_node(self, client):
        client._authenticated = True
        respx.delete(f"{API_URL}/labs/Test.unl/nodes/1").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success"},
            )
        )
        await client.delete_node("/Test.unl", 1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfig:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_node_config(self, client):
        client._authenticated = True
        config_text = "hostname R1\ninterface Ethernet1\n ip address 10.0.0.1/24"
        respx.get(f"{API_URL}/labs/Test.unl/nodes/1/config/startup").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {"data": config_text}, "status": "success"},
            )
        )
        result = await client.get_node_config("/Test.unl", 1)
        assert "hostname R1" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_node_config_empty(self, client):
        client._authenticated = True
        respx.get(f"{API_URL}/labs/Test.unl/nodes/1/config/startup").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {"data": ""}, "status": "success"},
            )
        )
        result = await client.get_node_config("/Test.unl", 1)
        assert result == ""

    @respx.mock
    @pytest.mark.asyncio
    async def test_push_node_config(self, client):
        client._authenticated = True
        respx.put(f"{API_URL}/labs/Test.unl/nodes/1/config/startup").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success", "message": "Config saved"},
            )
        )
        await client.push_node_config("/Test.unl", 1, "hostname R1")


# ---------------------------------------------------------------------------
# Networks & Interfaces
# ---------------------------------------------------------------------------


class TestNetworks:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_networks(self, client):
        client._authenticated = True
        networks = {
            "1": {"id": 1, "name": "Net-1", "type": "bridge"},
        }
        respx.get(f"{API_URL}/labs/Test.unl/networks").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": networks, "status": "success"},
            )
        )
        result = await client.list_networks("/Test.unl")
        assert "1" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_create_network(self, client):
        client._authenticated = True
        respx.post(f"{API_URL}/labs/Test.unl/networks").mock(
            return_value=httpx.Response(
                201,
                json={"code": 201, "data": {"id": 2}, "status": "success"},
            )
        )
        result = await client.create_network("/Test.unl", name="Backbone", network_type="bridge")
        assert result["id"] == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_network(self, client):
        client._authenticated = True
        respx.delete(f"{API_URL}/labs/Test.unl/networks/1").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success"},
            )
        )
        await client.delete_network("/Test.unl", 1)

    @respx.mock
    @pytest.mark.asyncio
    async def test_connect_interface(self, client):
        client._authenticated = True
        respx.put(f"{API_URL}/labs/Test.unl/nodes/1/interfaces").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": {}, "status": "success"},
            )
        )
        await client.connect_interface("/Test.unl", node_id=1, interface_id=0, network_id=1)

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_interfaces(self, client):
        client._authenticated = True
        ifaces = {
            "ethernet": [
                {"id": 0, "name": "e0", "network_id": 1},
                {"id": 1, "name": "e1", "network_id": 0},
            ]
        }
        respx.get(f"{API_URL}/labs/Test.unl/nodes/1/interfaces").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": ifaces, "status": "success"},
            )
        )
        result = await client.list_interfaces("/Test.unl", 1)
        assert "ethernet" in result
        assert len(result["ethernet"]) == 2


# ---------------------------------------------------------------------------
# Path Encoding
# ---------------------------------------------------------------------------


class TestPathEncoding:
    def test_encode_path_root(self):
        assert EveNGClient._encode_path("/") == "/"

    def test_encode_path_empty(self):
        assert EveNGClient._encode_path("") == "/"

    def test_encode_path_with_spaces(self):
        result = EveNGClient._encode_path("/My Folder/Sub Folder")
        assert "My%20Folder" in result
        assert "Sub%20Folder" in result

    def test_encode_lab_path_adds_unl(self):
        result = EveNGClient._encode_lab_path("/Test")
        assert result.endswith(".unl")

    def test_encode_lab_path_preserves_unl(self):
        result = EveNGClient._encode_lab_path("/Test.unl")
        assert result.count(".unl") == 1

    def test_encode_lab_path_with_spaces(self):
        result = EveNGClient._encode_lab_path("/My Lab.unl")
        assert "My%20Lab.unl" in result

    def test_encode_lab_path_adds_leading_slash(self):
        result = EveNGClient._encode_lab_path("Test.unl")
        assert result.startswith("/")

    def test_encode_lab_path_subfolder(self):
        result = EveNGClient._encode_lab_path("/networking/VOSS Lab.unl")
        assert "networking" in result
        assert "VOSS%20Lab.unl" in result


# ---------------------------------------------------------------------------
# Response Parsing
# ---------------------------------------------------------------------------


class TestResponseParsing:
    def test_parse_success_response(self, client):
        resp = httpx.Response(
            200,
            json={"code": 200, "data": {"id": 1}, "status": "success", "message": "OK"},
        )
        result = client._parse_response(resp)
        assert result == {"id": 1}

    def test_parse_201_response(self, client):
        resp = httpx.Response(
            201,
            json={"code": 201, "data": {"id": 5}, "status": "success", "message": "Created"},
        )
        result = client._parse_response(resp)
        assert result == {"id": 5}

    def test_parse_error_response(self, client):
        resp = httpx.Response(
            404,
            json={"code": 404, "data": None, "status": "fail", "message": "Lab not found"},
        )
        with pytest.raises(EveNGClientError) as exc_info:
            client._parse_response(resp)
        assert "Lab not found" in str(exc_info.value)
        assert exc_info.value.code == 404

    def test_parse_non_json_success(self, client):
        resp = httpx.Response(200, text="hostname R1\n")
        result = client._parse_response(resp)
        assert "hostname R1" in result

    def test_parse_non_json_error(self, client):
        resp = httpx.Response(500, text="Internal Server Error")
        with pytest.raises(EveNGClientError):
            client._parse_response(resp)

    def test_parse_no_data_field(self, client):
        """When data is missing, should return the full body dict."""
        resp = httpx.Response(
            200,
            json={"code": 200, "status": "success", "message": "Done"},
        )
        result = client._parse_response(resp)
        assert result["code"] == 200


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_error_attributes(self):
        err = EveNGClientError("test error", code=403, detail="forbidden")
        assert err.code == 403
        assert err.detail == "forbidden"
        assert "test error" in str(err)

    @respx.mock
    @pytest.mark.asyncio
    async def test_api_error_raises(self, client):
        client._authenticated = True
        respx.get(f"{API_URL}/labs/nonexistent.unl").mock(
            return_value=httpx.Response(
                404,
                json={"code": 404, "data": None, "status": "fail", "message": "Lab not found"},
            )
        )
        with pytest.raises(EveNGClientError):
            await client.get_lab("/nonexistent.unl")
