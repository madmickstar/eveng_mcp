"""Async HTTP client for the EVE-NG REST API.

Handles session-based authentication, cookie management, and all CRUD
operations on labs, nodes, and networks.

EVE-NG API reference: https://www.eve-ng.net/index.php/documentation/howtos/how-to-eve-ng-api/
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from .models import (
    AddNodeInput,
    EveApiResponse,
    Interface,
    Lab,
    Network,
    Node,
)

logger = logging.getLogger(__name__)


class EveNGClientError(Exception):
    """Raised when an EVE-NG API call fails."""

    def __init__(self, message: str, code: int = 0, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(message)


class EveNGClient:
    """Async client for the EVE-NG REST API.

    Uses session cookies for authentication.  Call `login()` before any other
    method.  The client keeps the httpx session open across calls so that the
    EVE-NG session cookie is reused automatically.

    Args:
        base_url: EVE-NG API base URL (e.g. ``http://192.168.122.10``).
        username: EVE-NG username (default ``admin``).
        password: EVE-NG password (default ``eve``).
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://192.168.122.10",
        username: str = "admin",
        password: str = "eve",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api",
            timeout=timeout,
            follow_redirects=True,
            # EVE-NG uses session cookies
            cookies=httpx.Cookies(),
        )
        self._authenticated = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def login(self) -> dict[str, Any]:
        """Authenticate with EVE-NG and store session cookie.

        Returns:
            Parsed JSON response from the auth endpoint.

        Raises:
            EveNGClientError: If authentication fails.
        """
        payload = {
            "username": self.username,
            "password": self.password,
            "html5": -1,
        }
        resp = await self._client.post("/auth/login", json=payload)
        data = self._parse_response(resp)
        self._authenticated = True
        logger.info("Authenticated with EVE-NG as %s", self.username)
        return data

    async def logout(self) -> None:
        """Destroy the EVE-NG session."""
        try:
            await self._client.get("/auth/logout")
        except httpx.HTTPError:
            pass  # best-effort
        self._authenticated = False

    async def close(self) -> None:
        """Logout and close the underlying HTTP client."""
        await self.logout()
        await self._client.aclose()

    async def ensure_authenticated(self) -> None:
        """Login if not already authenticated."""
        if not self._authenticated:
            await self.login()

    # ------------------------------------------------------------------
    # System / Status
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Get EVE-NG server status."""
        await self.ensure_authenticated()
        resp = await self._client.get("/status")
        return self._parse_response(resp)

    # ------------------------------------------------------------------
    # Images / Templates
    # ------------------------------------------------------------------

    async def list_node_templates(self) -> dict[str, Any]:
        """List all available node templates.

        Returns:
            Dictionary mapping template name to template details.
        """
        await self.ensure_authenticated()
        resp = await self._client.get("/list/templates/")
        return self._parse_response(resp)

    # ------------------------------------------------------------------
    # Labs
    # ------------------------------------------------------------------

    async def list_labs(self, folder: str = "/") -> list[dict[str, Any]]:
        """List labs in a folder.

        Args:
            folder: Folder path on EVE-NG (default ``/``).

        Returns:
            List of lab metadata dicts.
        """
        await self.ensure_authenticated()
        path = self._encode_path(folder)
        resp = await self._client.get(f"/folders{path}")
        data = self._parse_response(resp)
        # EVE-NG returns {"folders": [...], "labs": {...}}
        labs = data.get("labs", {}) if isinstance(data, dict) else {}
        return list(labs.values()) if isinstance(labs, dict) else labs

    async def get_lab(self, lab_path: str) -> dict[str, Any]:
        """Get lab metadata.

        Args:
            lab_path: Full lab path (e.g. ``/My Lab.unl``).
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}")
        return self._parse_response(resp)

    async def create_lab(
        self,
        name: str,
        path: str = "/",
        description: str = "",
        version: str = "1",
        author: str = "",
        body: str = "",
    ) -> dict[str, Any]:
        """Create a new lab.

        Args:
            name: Lab name (used as filename).
            path: Folder path where the lab will be created.
            description: Lab description.
            version: Lab version string.
            author: Author name.
            body: Lab notes.

        Returns:
            API response data.
        """
        await self.ensure_authenticated()
        payload = {
            "name": name,
            "version": version,
            "description": description,
            "author": author,
            "body": body,
            "path": path,
        }
        resp = await self._client.post("/labs", json=payload)
        return self._parse_response(resp)

    async def delete_lab(self, lab_path: str) -> dict[str, Any]:
        """Delete a lab.

        Args:
            lab_path: Full lab path (e.g. ``/My Lab.unl``).
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.delete(f"/labs{path}")
        return self._parse_response(resp)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def list_nodes(self, lab_path: str) -> dict[str, Any]:
        """List all nodes in a lab.

        Args:
            lab_path: Full lab path.

        Returns:
            Dictionary mapping node ID (string) to node details.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes")
        return self._parse_response(resp)

    async def get_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Get a single node's details.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes/{node_id}")
        return self._parse_response(resp)

    async def add_node(self, lab_path: str, node: AddNodeInput) -> dict[str, Any]:
        """Add a node to a lab.

        Args:
            lab_path: Full lab path.
            node: Node parameters.

        Returns:
            API response with the new node's ID.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        payload: dict[str, Any] = {
            "type": node.node_type,
            "template": node.template,
            "name": node.name,
            "ram": node.ram,
            "cpu": node.cpu,
            "ethernet": node.ethernet,
            "serial": node.serial,
            "console": node.console,
            "left": node.left,
            "top": node.top,
            "config": node.config,
            "delay": node.delay,
        }
        if node.image:
            payload["image"] = node.image
        # Remove empty/default name so EVE-NG auto-generates
        if not payload["name"]:
            del payload["name"]
        resp = await self._client.post(f"/labs{path}/nodes", json=payload)
        return self._parse_response(resp)

    async def delete_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Delete a node from a lab."""
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.delete(f"/labs{path}/nodes/{node_id}")
        return self._parse_response(resp)

    async def start_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Start a single node.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes/{node_id}/start")
        return self._parse_response(resp)

    async def stop_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Stop a single node.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes/{node_id}/stop")
        return self._parse_response(resp)

    async def start_all_nodes(self, lab_path: str) -> dict[str, Any]:
        """Start all nodes in a lab."""
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes/start")
        return self._parse_response(resp)

    async def stop_all_nodes(self, lab_path: str) -> dict[str, Any]:
        """Stop all nodes in a lab."""
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes/stop")
        return self._parse_response(resp)

    async def get_node_config(self, lab_path: str, node_id: int) -> str:
        """Get a node's startup configuration.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.

        Returns:
            Configuration text (may be empty if no config is set).
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes/{node_id}/config/startup")
        data = self._parse_response(resp)
        # EVE-NG returns config as {"data": "<config text>"} or just the string
        if isinstance(data, dict):
            return str(data.get("data", ""))
        return str(data) if data else ""

    async def push_node_config(
        self, lab_path: str, node_id: int, config: str
    ) -> dict[str, Any]:
        """Push startup configuration to a node.

        The node should be stopped before pushing config.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
            config: Full configuration text to set as startup config.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        payload = {"id": node_id, "data": config}
        resp = await self._client.put(
            f"/labs{path}/nodes/{node_id}/config/startup",
            json=payload,
        )
        return self._parse_response(resp)

    # ------------------------------------------------------------------
    # Interfaces
    # ------------------------------------------------------------------

    async def list_interfaces(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """List all interfaces on a node.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.

        Returns:
            Dictionary with 'ethernet' and/or 'serial' interface lists.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/nodes/{node_id}/interfaces")
        return self._parse_response(resp)

    async def connect_interface(
        self,
        lab_path: str,
        node_id: int,
        interface_id: int,
        network_id: int,
    ) -> dict[str, Any]:
        """Connect a node interface to a network.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
            interface_id: Interface ID on the node.
            network_id: Network ID to connect to.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        payload = {str(interface_id): str(network_id)}
        resp = await self._client.put(
            f"/labs{path}/nodes/{node_id}/interfaces",
            json=payload,
        )
        return self._parse_response(resp)

    # ------------------------------------------------------------------
    # Networks
    # ------------------------------------------------------------------

    async def list_networks(self, lab_path: str) -> dict[str, Any]:
        """List all networks in a lab.

        Args:
            lab_path: Full lab path.

        Returns:
            Dictionary mapping network ID to network details.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.get(f"/labs{path}/networks")
        return self._parse_response(resp)

    async def create_network(
        self,
        lab_path: str,
        name: str = "",
        network_type: str = "bridge",
        visibility: int = 1,
        left: int = 0,
        top: int = 0,
    ) -> dict[str, Any]:
        """Create a network in a lab.

        Args:
            lab_path: Full lab path.
            name: Network display name.
            network_type: Type of network (bridge, ovs, pnet0-pnet9).
            visibility: 1=visible, 0=hidden.
            left: Canvas X position.
            top: Canvas Y position.

        Returns:
            API response with the new network's ID.
        """
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        payload = {
            "name": name or "Net",
            "type": network_type,
            "visibility": visibility,
            "left": left,
            "top": top,
        }
        resp = await self._client.post(f"/labs{path}/networks", json=payload)
        return self._parse_response(resp)

    async def delete_network(self, lab_path: str, network_id: int) -> dict[str, Any]:
        """Delete a network from a lab."""
        await self.ensure_authenticated()
        path = self._encode_lab_path(lab_path)
        resp = await self._client.delete(f"/labs{path}/networks/{network_id}")
        return self._parse_response(resp)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_path(path: str) -> str:
        """URL-encode a folder path for the EVE-NG API.

        EVE-NG expects paths like ``/`` or ``/My%20Folder``.
        """
        if not path or path == "/":
            return "/"
        # Strip trailing slash, ensure leading slash
        path = "/" + path.strip("/")
        # Encode each segment
        segments = path.split("/")
        return "/".join(quote(s, safe="") for s in segments)

    @staticmethod
    def _encode_lab_path(lab_path: str) -> str:
        """URL-encode a full lab path.

        Lab paths include the .unl extension.  If the caller omits it,
        we append it automatically.

        Examples:
            ``/My Lab.unl`` -> ``/My%20Lab.unl``
            ``/folder/lab`` -> ``/folder/lab.unl``
        """
        if not lab_path.endswith(".unl"):
            lab_path = lab_path + ".unl"
        # Ensure leading slash
        if not lab_path.startswith("/"):
            lab_path = "/" + lab_path
        segments = lab_path.split("/")
        return "/".join(quote(s, safe="") for s in segments)

    def _parse_response(self, resp: httpx.Response) -> Any:
        """Parse an EVE-NG API response.

        EVE-NG wraps all responses in ``{"code": ..., "data": ..., "status": ..., "message": ...}``.
        On success, we extract and return the ``data`` field.
        On failure, we raise :class:`EveNGClientError`.

        Args:
            resp: Raw httpx response.

        Returns:
            The ``data`` field from the JSON response.

        Raises:
            EveNGClientError: If the response indicates an error.
        """
        # Some endpoints return 200 with an error in the body
        try:
            body = resp.json()
        except Exception:
            # Non-JSON responses (e.g. plain text config)
            if resp.is_success:
                return resp.text
            raise EveNGClientError(
                f"EVE-NG returned HTTP {resp.status_code} with non-JSON body",
                code=resp.status_code,
                detail=resp.text[:500],
            )

        code = body.get("code", resp.status_code)
        status = body.get("status", "")
        message = body.get("message", "")

        # EVE-NG uses code 200/201 for success
        if code in (200, 201) or status == "success":
            return body.get("data", body)

        raise EveNGClientError(
            f"EVE-NG API error (code={code}): {message}",
            code=code,
            detail=str(body),
        )

    def __repr__(self) -> str:
        return f"EveNGClient(base_url={self.base_url!r}, user={self.username!r})"
