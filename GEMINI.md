# GEMINI.md - Project Overview: BlenderMCP

This document provides a comprehensive overview of the BlenderMCP project for AI-assisted development.

## 1. Project Overview

**BlenderMCP** is a Python project that connects Blender to a large language model (like Gemini or Claude) using the Model Context Protocol (MCP). It enables AI-assisted 3D modeling, allowing the AI to directly inspect and manipulate a Blender scene.

The project consists of two main components:

1.  **Blender Addon (`addon.py`):** A script that runs inside Blender. It starts a simple TCP socket server that listens for JSON-based commands to execute using Blender's Python API (`bpy`). It also provides the UI panel within Blender for managing the connection and API keys.
2.  **MCP Server (`src/blender_mcp/server.py`):** A Python server that runs in the user's terminal. This server implements the Model Context Protocol, exposing a set of "tools" that the AI can call. When a tool is called, the MCP server sends the corresponding command to the Blender addon's socket server.

The project also integrates with several third-party APIs for asset creation:
*   **Poly Haven:** For downloading and importing HDRIs, textures, and models.
*   **Sketchfab:** For searching and downloading a vast library of 3D models.
*   **Hyper3D (Rodin):** For generating 3D models from text prompts or images.

## 2. Building and Running

This is a Python project managed with `uv`.

### Prerequisites

*   Blender 3.0+
*   Python 3.10+
*   `uv` package manager installed.

### Running the Project

The system requires two components to be running simultaneously: the Blender addon and the MCP server.

**A. Running the MCP Server:**

The server is defined as a script in `pyproject.toml`. To run it, execute the following command in your terminal:

```bash
uvx blender-mcp
```

This command starts the MCP server, which will then be available for an AI model to connect to. The server listens for connections from the Blender addon on `localhost:9876` by default.

**B. Installing and Running the Blender Addon:**

1.  Download or locate the `addon.py` file from the project root.
2.  Open Blender.
3.  Go to `Edit > Preferences > Add-ons`.
4.  Click "Install..." and select the `addon.py` file.
5.  Enable the addon by checking the box next to "Interface: Blender MCP".
6.  In the 3D Viewport, open the sidebar (press 'N').
7.  Find the "BlenderMCP" tab.
8.  (Optional) Enable and configure API keys for Poly Haven, Sketchfab, or Hyper3D.
9.  Click **"Connect to MCP server"**.

Once both are running, the AI can use the provided tools to interact with Blender.

## 3. Development Conventions

*   **Dependencies:** Project dependencies are managed in `pyproject.toml` and locked in `uv.lock`. The primary dependency is `mcp[cli]`, which provides the framework for the MCP server.
*   **Structure:**
    *   `addon.py`: The self-contained Blender addon.
    *   `src/blender_mcp/`: The source code for the Python package.
    *   `src/blender_mcp/server.py`: The main entry point for the MCP server, containing all tool definitions and the connection logic to the Blender addon.
*   **Communication Protocol:** The MCP server (`server.py`) and the Blender addon (`addon.py`) communicate over a TCP socket using a simple JSON-based protocol.
    *   Commands are JSON objects with a `type` and `params`.
    *   Responses are JSON objects with a `status` and `result` or `message`.
*   **Blender API Usage:** The `addon.py` script uses `bpy.app.timers.register` to ensure that all commands received from the socket are executed on Blender's main thread, which is a requirement for safely using the `bpy` API.
