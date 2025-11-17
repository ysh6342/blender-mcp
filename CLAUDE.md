# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BlenderMCP is a Model Context Protocol (MCP) server that connects Blender to AI assistants like Claude. It enables AI-assisted 3D modeling by allowing direct inspection and manipulation of Blender scenes through a socket-based communication protocol.

**Architecture:** The system consists of two communicating components:
1. **Blender Addon** (`addon.py`): Runs inside Blender as a TCP socket server (default: localhost:9876) that receives JSON commands and executes them using Blender's Python API (`bpy`)
2. **MCP Server** (`src/blender_mcp/server.py`): Implements the Model Context Protocol, exposing tools that AI assistants can call. Communicates with the Blender addon via socket connection

**Communication Flow:** AI Assistant → MCP Server (via MCP protocol) → Blender Addon (via TCP socket + JSON) → Blender API (`bpy`)

## Running the Project

### Start MCP Server
```bash
uvx blender-mcp
```

This launches the MCP server which listens for connections from the Blender addon on `localhost:9876` (configurable via `BLENDER_HOST` and `BLENDER_PORT` environment variables).

### Install Blender Addon
1. Open Blender
2. Edit > Preferences > Add-ons > Install... → Select `addon.py`
3. Enable "Interface: Blender MCP"
4. In 3D Viewport sidebar (N), go to BlenderMCP tab
5. Click "Connect to Claude"

Both components must be running simultaneously for the integration to work.

## Code Architecture

### Socket Communication Protocol
- **Command format:** `{"type": "command_name", "params": {...}}`
- **Response format:** `{"status": "success|error", "result": {...}}`
- All Blender API commands are executed on the main thread using `bpy.app.timers.register()` to ensure thread safety

### MCP Server (`src/blender_mcp/server.py`)
- Built with FastMCP framework (`mcp[cli]` dependency)
- Uses global persistent connection (`_blender_connection`) to maintain socket with Blender addon
- Tools are decorated with `@mcp.tool()` and automatically exposed to AI assistants
- Prompts use `@mcp.prompt()` to provide reusable guidance (e.g., asset creation strategy)
- Implements chunked response handling for large data transfers from Blender

### Blender Addon (`addon.py`)
- Self-contained single-file addon (includes all rigging functionality inline)
- Server runs in separate thread (`threading.Thread`), client handlers in per-connection threads
- Command handlers conditionally enabled based on UI checkboxes (`blendermcp_use_polyhaven`, `blendermcp_use_hyper3d`, `blendermcp_use_sketchfab`)
- Integrates with external APIs:
  - **Poly Haven**: HDRIs, textures, models (requires User-Agent header)
  - **Sketchfab**: Model search and download
  - **Hyper3D Rodin**: AI-generated 3D models from text/images

### Rigging System
Advanced rigging tools for humanoid characters are implemented directly in `addon.py` (lines 20-733):
- **Auto-detection**: Finds humanoid meshes/armatures by bone count and vertex count heuristics
- **Rig type detection**: Identifies Mixamo, generic humanoid, or mesh-only rigs by bone naming conventions
- **Normalized structure**: Abstracts different rig types into standardized bone mappings
- **Finger rigging**: Creates/fixes finger bones with automatic weighting
- **UE5 export**: Renames bones to Unreal Engine 5 skeleton conventions and exports FBX with proper settings

Key rigging functions (all in `addon.py`):
- `rigging_inspect_humanoid_rig()`: Analyzes rig structure and returns normalized description
- `rigging_auto_rig_meshy_character()`: Creates basic armature for mesh-only characters
- `rigging_ensure_finger_chains_for_hand()`: Adds missing finger bones
- `rigging_auto_weight_fingers_only()`: Applies automatic weights to finger bones
- `rigging_rename_fingers_to_ue5()`: Renames bones for UE5 compatibility
- `rigging_export_ue5_ready_fbx()`: Exports with UE5-optimized settings

## Development Commands

### Package Management
```bash
# Install/update dependencies
uv sync

# Run server directly
python -m blender_mcp.server

# Build package
python -m build
```

### Testing Connection
1. Start MCP server: `uvx blender-mcp`
2. In Blender addon panel, click "Connect to Claude"
3. Check server logs for connection confirmation
4. Test with a simple command through AI assistant

## Key Implementation Details

### Adding New MCP Tools
1. Define function in `server.py` with `@mcp.tool()` decorator
2. Add corresponding command handler in `addon.py`'s `_execute_command_internal()` method
3. Handler must return dict with command results
4. Update handlers dict to map command type to handler function

Example:
```python
# In server.py
@mcp.tool()
def my_new_tool(ctx: Context, param: str) -> str:
    blender = get_blender_connection()
    result = blender.send_command("my_command", {"param": param})
    return json.dumps(result, indent=2)

# In addon.py, add to handlers dict:
handlers = {
    "my_command": self.my_handler,
    # ...
}

def my_handler(self, param):
    # Use bpy API here
    return {"result": "..."}
```

### Handling Large Responses
The socket implementation uses `receive_full_response()` with chunked reading and JSON validation to handle responses of any size. Timeout is 15 seconds to accommodate complex Blender operations.

### Third-Party API Integration
External API integrations (Poly Haven, Sketchfab, Hyper3D) are:
- Controlled by boolean properties in Blender addon UI
- Only exposed as MCP tools when enabled via `blendermcp_use_*` scene properties
- Checked on each connection via `get_*_status()` commands
- Poly Haven requires `User-Agent: blender-mcp` header (stored in `REQ_HEADERS`)

### Asset Creation Strategy
The MCP server includes a prompt (`asset_creation_strategy()`) that defines the recommended workflow:
1. Check integration status (Poly Haven, Sketchfab, Hyper3D)
2. Prefer external assets over primitive scripting
3. Use `world_bounding_box` to verify spatial relationships
4. Priority: Sketchfab/Poly Haven → Hyper3D → Manual scripting

## Important Notes

- **Thread Safety**: All `bpy` operations must execute on main thread (use `bpy.app.timers.register`)
- **Socket Reconnection**: Connection auto-recreates on failure; avoid manual reconnect logic
- **Security**: `execute_code` tool allows arbitrary Python execution - warn users to save work first
- **API Keys**: Hyper3D includes free trial key (`RODIN_FREE_TRIAL_KEY`), but has daily limits
- **Scene Info Limits**: `get_scene_info()` returns max 10 objects to prevent overwhelming responses
- **Addon is Self-Contained**: All rigging code is embedded in `addon.py` (not in `src/blender_mcp/rigging/`)
- **Windows Support**: Use `cmd /c uvx blender-mcp` in Windows MCP configurations
