"""Async HTTP client for the EVE-NG REST API.

Handles session-based authentication, cookie management, and all CRUD
operations on labs, nodes, and networks.

EVE-NG API reference: https://www.eve-ng.net/index.php/documentation/howtos/how-to-eve-ng-api/
"""

from __future__ import annotations

import asyncio
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


class EveNGSessionError(EveNGClientError):
    """Raised when the EVE-NG session cookie is no longer valid.

    This is distinct from a generic :class:`EveNGClientError` so that
    :meth:`EveNGClient._request` can catch *only* auth failures and
    transparently recover by re-authenticating, instead of retrying on
    every kind of API error (bad payloads, missing labs, etc.).
    """


class EveNGConsoleError(Exception):
    """Raised when a console (telnet) session to a node fails."""


_IAC = 255  # Telnet "Interpret As Command"


async def telnet_send_commands(
    host: str,
    port: int,
    commands: list[str],
    timeout: float = 10.0,
    settle: float = 0.8,
) -> str:
    """Open a raw telnet session to a node's console and run a sequence of commands.

    This talks directly to the emulated device's own console port (the same
    ``telnet://host:port`` EVE-NG exposes per node once it is running) —
    it does not use the EVE-NG REST API at all. EVE-NG's documented API has
    no endpoint for pushing arbitrary configuration into a running device;
    the supported way to change a device's config is to drive its CLI over
    console, then persist it on-device (e.g. ``write memory``). This helper
    automates exactly that.

    Telnet option-negotiation sequences (IAC/WILL/WONT/DO/DONT) sent by the
    device are stripped from the captured output rather than answered, which
    is sufficient for the simple console servers QEMU/Dynamips/IOL nodes
    expose — these devices don't typically enforce strict negotiation.

    Args:
        host: Node console host (from the node's ``url`` field).
        port: Node console TCP port (from the node's ``url`` field).
        commands: Lines to send in order, e.g. ``["enable", "configure
            terminal", "vlan 20", " name testvlan", "exit", "write memory"]``.
        timeout: Timeout in seconds for establishing the connection.
        settle: Seconds to wait for a response after each command before
            sending the next one. Increase this if a device is slow to
            respond (e.g. right after boot).

    Returns:
        The captured console output as text, negotiation bytes stripped.

    Raises:
        EveNGConsoleError: If the connection fails or times out.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise EveNGConsoleError(
            f"Could not connect to console {host}:{port}: {exc}"
        ) from exc

    output = bytearray()

    async def _drain() -> None:
        """Read whatever the device sends until it goes quiet for `settle` seconds."""
        try:
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=settle)
                if not chunk:
                    break
                output.extend(chunk)
        except asyncio.TimeoutError:
            pass  # device has gone quiet — assume it's done responding for now

    try:
        await _drain()  # initial banner / telnet negotiation
        for cmd in commands:
            writer.write((cmd + "\r\n").encode())
            await writer.drain()
            await _drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass  # best-effort close

    # Strip 3-byte telnet IAC negotiation sequences (IAC + command + option)
    cleaned = bytearray()
    i = 0
    while i < len(output):
        if output[i] == _IAC and i + 2 < len(output):
            i += 3
            continue
        cleaned.append(output[i])
        i += 1

    return cleaned.decode(errors="replace")


class EveNGClient:
    """Async client for the EVE-NG REST API.

    Uses session cookies for authentication. The client keeps the httpx
    session open across calls so that the EVE-NG session cookie is reused
    automatically. If the session cookie expires or is evicted mid-run
    (e.g. by a proxy dropping ``Set-Cookie``, a server-side timeout, or
    another login to the same account), every method transparently
    re-authenticates once and retries the failed request via
    :meth:`_request`, rather than surfacing a hard failure to the caller.

    Args:
        base_url: EVE-NG API base URL (e.g. ``http://192.168.122.10``).
        username: EVE-NG username (default ``admin``).
        password: EVE-NG password (default ``eve``).
        timeout: Request timeout in seconds.
        verify_ssl: Whether to verify the server's TLS certificate. EVE-NG
            deployments commonly run behind a self-signed certificate, so
            this defaults to ``False``. Set to ``True`` (or pass a CA bundle
            path via a custom httpx client) if your server has a certificate
            issued by a trusted CA.
    """

    def __init__(
        self,
        base_url: str = "http://192.168.122.10",
        username: str = "admin",
        password: str = "eve",
        timeout: float = 30.0,
        verify_ssl: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api",
            timeout=timeout,
            follow_redirects=True,
            verify=verify_ssl,
            # EVE-NG uses session cookies
            cookies=httpx.Cookies(),
        )
        self._authenticated = False
        if not verify_ssl:
            logger.warning(
                "TLS certificate verification is disabled for %s — "
                "expected for EVE-NG's default self-signed certificate, "
                "but set verify_ssl=True if this server has a CA-issued cert.",
                self.base_url,
            )

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
        """Login if this client has never authenticated yet.

        This only covers the *initial* login. Recovery from a session that
        was valid but later died (timeout, eviction, dropped cookie) is
        handled separately by :meth:`_request`, which retries after a
        fresh login rather than relying on this flag alone.
        """
        if not self._authenticated:
            await self.login()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request, recovering from a dead session.

        Ensures the client is logged in, issues the request, and if the
        response indicates the session cookie is no longer valid
        (:class:`EveNGSessionError`), re-authenticates once and retries the
        exact same request. A second failure after the retry is raised to
        the caller rather than looping indefinitely.

        Args:
            method: HTTP method, e.g. ``"GET"``, ``"POST"``, ``"PUT"``, ``"DELETE"``.
            path: API path relative to ``/api`` (e.g. ``"/labs/foo.unl/nodes"``).
            **kwargs: Passed through to ``httpx.AsyncClient.request`` (e.g. ``json=...``).

        Returns:
            The parsed ``data`` field of the EVE-NG response (see :meth:`_parse_response`).

        Raises:
            EveNGClientError: For any non-recoverable API error, or if the
                retried request still fails after re-authentication.
        """
        await self.ensure_authenticated()
        resp = await self._client.request(method, path, **kwargs)
        try:
            return self._parse_response(resp)
        except EveNGSessionError:
            logger.warning(
                "EVE-NG session expired or rejected, re-authenticating and "
                "retrying: %s %s",
                method,
                path,
            )
            self._authenticated = False
            await self.login()
            resp = await self._client.request(method, path, **kwargs)
            # Let a second failure propagate — avoids retry loops if creds
            # are wrong or the server is genuinely down.
            return self._parse_response(resp)

    # ------------------------------------------------------------------
    # System / Status
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Get EVE-NG server status."""
        return await self._request("GET", "/status")

    # ------------------------------------------------------------------
    # Images / Templates
    # ------------------------------------------------------------------

    async def list_node_templates(self) -> dict[str, Any]:
        """List all available node templates.

        Returns:
            Dictionary mapping template name to template details.
        """
        return await self._request("GET", "/list/templates/")

    # ------------------------------------------------------------------
    # Labs
    # ------------------------------------------------------------------

    async def list_folder_contents(self, folder: str = "/") -> dict[str, Any]:
        """List both subfolders and labs directly inside a folder.

        Unlike :meth:`list_labs`, which discards the ``folders`` array from
        the API response, this returns both so callers can browse or
        recursively walk the folder tree.

        Args:
            folder: Folder path on EVE-NG (default ``/``).

        Returns:
            ``{"folders": [...], "labs": [...]}`` — subfolders (each with at
            least a ``path``/``name``) and labs directly inside ``folder``
            (not recursive).
        """
        path = self._encode_path(folder)
        data = await self._request("GET", f"/folders{path}")
        folders = data.get("folders", []) if isinstance(data, dict) else []
        labs = data.get("labs", {}) if isinstance(data, dict) else {}
        return {
            "folders": folders,
            "labs": list(labs.values()) if isinstance(labs, dict) else labs,
        }

    async def list_labs(self, folder: str = "/") -> list[dict[str, Any]]:
        """List labs in a folder.

        Args:
            folder: Folder path on EVE-NG (default ``/``).

        Returns:
            List of lab metadata dicts.
        """
        path = self._encode_path(folder)
        data = await self._request("GET", f"/folders{path}")
        # EVE-NG returns {"folders": [...], "labs": {...}}
        labs = data.get("labs", {}) if isinstance(data, dict) else {}
        return list(labs.values()) if isinstance(labs, dict) else labs

    async def get_lab(self, lab_path: str) -> dict[str, Any]:
        """Get lab metadata.

        Args:
            lab_path: Full lab path (e.g. ``/My Lab.unl``).
        """
        path = self._encode_lab_path(lab_path)
        return await self._request("GET", f"/labs{path}")

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
        payload = {
            "name": name,
            "version": version,
            "description": description,
            "author": author,
            "body": body,
            "path": path,
        }
        return await self._request("POST", "/labs", json=payload)

    async def edit_lab(self, lab_path: str, **fields: Any) -> dict[str, Any]:
        """Edit an existing lab's metadata.

        Per EVE-NG's API, this sets one field at a time — pass exactly one
        keyword argument (e.g. ``description="new text"``). Valid fields
        include ``name``, ``version``, ``author``, ``description``, ``body``.

        Args:
            lab_path: Full lab path (e.g. ``/My Lab.unl``).
            **fields: Exactly one field to update, e.g. ``description="..."``.

        Returns:
            API response data.

        Raises:
            ValueError: If zero or more than one field is passed.
        """
        if len(fields) != 1:
            raise ValueError(
                "edit_lab sets exactly one field at a time per EVE-NG's API "
                f"(got {list(fields.keys())})"
            )
        path = self._encode_lab_path(lab_path)
        return await self._request("PUT", f"/labs{path}", json=fields)

    async def delete_lab(self, lab_path: str) -> dict[str, Any]:
        """Delete a lab.

        Args:
            lab_path: Full lab path (e.g. ``/My Lab.unl``).
        """
        path = self._encode_lab_path(lab_path)
        return await self._request("DELETE", f"/labs{path}")

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
        path = self._encode_lab_path(lab_path)
        return await self._request("GET", f"/labs{path}/nodes")

    async def get_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Get a single node's details.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
        """
        path = self._encode_lab_path(lab_path)
        return await self._request("GET", f"/labs{path}/nodes/{node_id}")

    async def add_node(self, lab_path: str, node: AddNodeInput) -> dict[str, Any]:
        """Add a node to a lab.

        Args:
            lab_path: Full lab path.
            node: Node parameters.

        Returns:
            API response with the new node's ID.
        """
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
        return await self._request("POST", f"/labs{path}/nodes", json=payload)

    async def delete_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Delete a node from a lab."""
        path = self._encode_lab_path(lab_path)
        return await self._request("DELETE", f"/labs{path}/nodes/{node_id}")

    async def start_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Start a single node.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
        """
        path = self._encode_lab_path(lab_path)
        return await self._request("GET", f"/labs{path}/nodes/{node_id}/start")

    async def stop_node(self, lab_path: str, node_id: int) -> dict[str, Any]:
        """Stop a single node.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.
        """
        path = self._encode_lab_path(lab_path)
        return await self._request("GET", f"/labs{path}/nodes/{node_id}/stop")

    async def start_all_nodes(self, lab_path: str) -> dict[str, Any]:
        """Start every node in a lab.

        EVE-NG's bulk ``/nodes/start`` endpoint returns a generic
        ``"Request not valid (60027)"`` route-dispatcher error on some
        EVE-NG versions/deployments, even though per-node start works fine.
        To stay version-agnostic, this lists the lab's nodes and starts each
        one individually via :meth:`start_node` rather than depending on the
        bulk route.

        Args:
            lab_path: Full lab path.

        Returns:
            A summary dict: ``{"status": "success"|"partial", "started":
            [...], "errors": {node_id: message}}``.
        """
        nodes = await self.list_nodes(lab_path)
        node_ids = list(nodes.keys()) if isinstance(nodes, dict) else []
        started: list[str] = []
        errors: dict[str, str] = {}
        for node_id in node_ids:
            try:
                await self.start_node(lab_path, int(node_id))
                started.append(node_id)
            except EveNGClientError as exc:
                errors[node_id] = str(exc)
        return {
            "status": "success" if not errors else "partial",
            "started": started,
            "errors": errors,
        }

    async def stop_all_nodes(self, lab_path: str) -> dict[str, Any]:
        """Stop every node in a lab.

        Same rationale as :meth:`start_all_nodes` — iterates per-node via
        :meth:`stop_node` rather than the bulk ``/nodes/stop`` endpoint.

        Args:
            lab_path: Full lab path.

        Returns:
            A summary dict: ``{"status": "success"|"partial", "stopped":
            [...], "errors": {node_id: message}}``.
        """
        nodes = await self.list_nodes(lab_path)
        node_ids = list(nodes.keys()) if isinstance(nodes, dict) else []
        stopped: list[str] = []
        errors: dict[str, str] = {}
        for node_id in node_ids:
            try:
                await self.stop_node(lab_path, int(node_id))
                stopped.append(node_id)
            except EveNGClientError as exc:
                errors[node_id] = str(exc)
        return {
            "status": "success" if not errors else "partial",
            "stopped": stopped,
            "errors": errors,
        }

    async def get_node_config(self, lab_path: str, node_id: int) -> str:
        """Get a node's startup configuration.

        Args:
            lab_path: Full lab path.
            node_id: Numeric node ID.

        Returns:
            Configuration text (may be empty if no config is set).
        """
        path = self._encode_lab_path(lab_path)
        data = await self._request(
            "GET", f"/labs{path}/nodes/{node_id}/config/startup"
        )
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
        path = self._encode_lab_path(lab_path)
        payload = {"id": node_id, "data": config}
        return await self._request(
            "PUT", f"/labs{path}/nodes/{node_id}/config/startup", json=payload
        )

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
        path = self._encode_lab_path(lab_path)
        return await self._request("GET", f"/labs{path}/nodes/{node_id}/interfaces")

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
        path = self._encode_lab_path(lab_path)
        payload = {str(interface_id): str(network_id)}
        return await self._request(
            "PUT", f"/labs{path}/nodes/{node_id}/interfaces", json=payload
        )

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
        path = self._encode_lab_path(lab_path)
        return await self._request("GET", f"/labs{path}/networks")

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
        path = self._encode_lab_path(lab_path)
        payload = {
            "name": name or "Net",
            "type": network_type,
            "visibility": visibility,
            "left": left,
            "top": top,
        }
        return await self._request("POST", f"/labs{path}/networks", json=payload)

    async def delete_network(self, lab_path: str, network_id: int) -> dict[str, Any]:
        """Delete a network from a lab."""
        path = self._encode_lab_path(lab_path)
        return await self._request("DELETE", f"/labs{path}/networks/{network_id}")

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
        On failure, we raise :class:`EveNGSessionError` if the failure looks
        like a dead/rejected session (so :meth:`_request` can recover), or
        :class:`EveNGClientError` for any other API error.

        Args:
            resp: Raw httpx response.

        Returns:
            The ``data`` field from the JSON response.

        Raises:
            EveNGSessionError: If the response indicates the session is invalid.
            EveNGClientError: If the response indicates any other error.
        """
        # Some endpoints return 200 with an error in the body
        try:
            body = resp.json()
        except Exception:
            # Non-JSON responses (e.g. plain text config)
            if resp.is_success:
                return resp.text
            if resp.status_code in (401, 403):
                raise EveNGSessionError(
                    f"EVE-NG session rejected (HTTP {resp.status_code})",
                    code=resp.status_code,
                    detail=resp.text[:500],
                )
            raise EveNGClientError(
                f"EVE-NG returned HTTP {resp.status_code} with non-JSON body",
                code=resp.status_code,
                detail=resp.text[:500],
            )

        code = body.get("code", resp.status_code)
        status = body.get("status", "")
        message = str(body.get("message", ""))

        # EVE-NG uses code 200/201 for success
        if code in (200, 201) or status == "success":
            return body.get("data", body)

        # Treat both transport-level 401/403 and EVE-NG's "200 OK but
        # status: fail" auth errors as a recoverable session failure.
        # EVE-NG uses code 412 specifically for "not authenticated / session
        # timed out" (e.g. internal message code 90001), separately from the
        # more conventional 400/401/403 range, so it must be checked on its
        # own rather than only via the code-plus-keyword combination below.
        session_dead = (
            resp.status_code in (401, 403)
            or code in (401, 403, 412)
            or any(
                kw in message.lower()
                for kw in ("logged in", "session", "unauthorized", "not authenticated")
            )
        )
        if session_dead:
            raise EveNGSessionError(
                f"EVE-NG session expired (code={code}): {message}",
                code=code,
                detail=str(body),
            )

        raise EveNGClientError(
            f"EVE-NG API error (code={code}): {message}",
            code=code,
            detail=str(body),
        )

    def __repr__(self) -> str:
        return f"EveNGClient(base_url={self.base_url!r}, user={self.username!r})"
