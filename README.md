# eveng_mcp

An MCP (Model Context Protocol) server that gives AI agents (e.g. Claude
Desktop) programmatic access to [EVE-NG](https://www.eve-ng.net/) network
labs — create, configure, and manage virtual network topologies through
natural-language requests.

This is a fork of
[axiom-works-ai/eveng-mcp-server](https://github.com/axiom-works-ai/eveng-mcp-server)
with a set of reliability fixes and new tools layered on top (see
[Changes in this fork](#changes-in-this-fork) below).

## Configuration

Set these environment variables in your MCP client config (e.g. Claude
Desktop's `claude_desktop_config.json`):

| Variable | Default | Description |
|---|---|---|
| `EVENG_HOST` | `http://192.168.122.10` | Base URL of the EVE-NG server |
| `EVENG_USERNAME` | `admin` | API username |
| `EVENG_PASSWORD` | `eve` | API password |
| `EVENG_VERIFY_SSL` | `false` | Verify the server's TLS certificate (`true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off`). Defaults to `false` since EVE-NG typically ships a self-signed certificate. |

**Note on accounts:** EVE-NG allows only one active session per user account.
If the account used here is also logged into the EVE-NG web UI elsewhere,
each side will periodically evict the other's session. It's recommended to
give this MCP server its own dedicated EVE-NG user, separate from any
account you browse the UI with.

## Available tools

### Lab management
- **`list_labs(folder="/")`** — list labs directly inside one folder.
- **`list_all_labs(folder="/")`** *(new)* — recursively walk the full folder
  tree from `folder` down, returning every subfolder and the labs inside it
  at every level (not just the top level).
- **`get_lab(lab_path)`** — full lab detail: metadata, nodes, and networks.
- **`create_lab(name, description, path, author, version, body)`** — create
  a new lab.
- **`edit_lab(lab_path, field, value)`** *(new)* — update one metadata field
  on an existing lab (`name`, `version`, `author`, `description`, or `body`).
  EVE-NG's API only accepts a single field per edit call.
- **`delete_lab(lab_path)`** — delete a lab. Irreversible.

### Images / templates
- **`list_images()`** — list available node templates/images.

### Node management
- **`add_node(...)`** — add a node to a lab.
- **`start_node(lab_path, node_id)`** / **`stop_node(lab_path, node_id)`** —
  start/stop a single node.
- **`start_all(lab_path)`** / **`stop_all(lab_path)`** — start/stop every
  node in a lab. *(Rewritten — see Fixes below.)*
- **`get_node_status(lab_path, node_id)`** — node status and details
  (RAM, CPU, template, console URL, running/stopped/building).

### Interfaces & connectivity
- **`list_interfaces(lab_path, node_id)`** *(new)* — list a node's
  interfaces and which network (if any) each is connected to.
- **`connect_nodes(...)`** — connect two node interfaces via a shared
  network (creates the network and wires both sides).

### Configuration
- **`get_node_config(lab_path, node_id)`** / **`push_config(lab_path,
  node_id, config)`** — read/write a node's startup configuration via
  EVE-NG's config API.
- **`send_console_commands(lab_path, node_id, commands)`** *(new)* — run a
  sequence of CLI commands directly against a node's console over telnet.
  EVE-NG's REST API has no reliable config-push path for many device types,
  so this drives the device's own CLI instead (the same way you would by
  hand), and is the recommended way to make live config changes (VLANs,
  interfaces, routing, etc.). Include a persistence command such as
  `write memory` as the last command if the change should survive a reload.

## Changes in this fork

### Fixes
- **Session reconnect.** The upstream client's `_authenticated` flag was a
  one-way switch: once set `True` after the first login, it was never
  re-checked, so if EVE-NG's session cookie later expired or was evicted
  (server-side timeout, another login to the same account, a proxy dropping
  `Set-Cookie`), every subsequent call failed outright with no recovery.
  Every request now goes through a central `_request()` helper that detects
  a dead session (`EveNGSessionError`) — including EVE-NG's `code: 412`
  "session timed out" response, which isn't in the conventional 401/403
  range — and transparently re-authenticates and retries once before
  surfacing an error.
- **`start_all` / `stop_all` reliability.** EVE-NG's bulk `/nodes/start` and
  `/nodes/stop` endpoints returned a generic route-dispatcher error
  (`code=400`, "Request not valid") on this deployment, even though starting
  or stopping nodes individually worked fine. Both tools now list the lab's
  nodes and start/stop each one individually instead of depending on the
  bulk endpoint, and return a summary of which nodes succeeded and which
  errored.
- **TLS verification made explicit and configurable.** The client previously
  verified certificates by default, which hard-fails against EVE-NG's
  typical self-signed certificate. `verify_ssl` is now a constructor
  parameter (default `False`), wired to the `EVENG_VERIFY_SSL` environment
  variable.

### New capabilities
- `list_interfaces` — existed in the HTTP client but was never registered
  as an MCP tool; now exposed.
- `list_all_labs` — recursive folder/lab tree listing, since `list_labs`
  only ever showed one folder at a time and discarded the `folders` array
  from EVE-NG's response entirely. Includes cycle detection and a hard
  depth limit to guard against folder listings that reference themselves
  or a parent.
- `edit_lab` — lab metadata editing wasn't exposed at all previously.
- `send_console_commands` — a raw telnet helper (`telnet_send_commands` in
  `client.py`) plus MCP tool for driving a node's CLI directly, since
  EVE-NG's documented API has no general config-push endpoint for most
  device types.

## Known limitations / things to watch for

- `add_node` can return an opaque `HTTP 500` with no JSON body for some
  templates (e.g. `vmx`) if an explicit `image` isn't supplied — check
  `list_images` (or an existing node using the same template) for the exact
  image string your server has installed.
- Lab-modifying calls can fail with `"Failed to lock the lab (60061)"` if
  the lab is open in the EVE-NG web UI elsewhere, or if a prior failed
  request left a stale lock. Close the lab in the UI and retry; if it
  persists, check the EVE-NG server for a stale lock file or logs around
  the failing request.
