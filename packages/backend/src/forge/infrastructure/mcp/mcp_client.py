"""MCP (Model Context Protocol) client — stdio and HTTP transports.

Implements JSON-RPC 2.0 over two transports:
- ``StdioTransport``: spawns a subprocess and communicates via stdin/stdout.
- ``HTTPTransport``: sends POST requests to an HTTP MCP server.

The high-level ``MCPClient`` wraps a transport and provides methods for the
MCP handshake (initialize), tool discovery (list_tools), and tool invocation
(call_tool).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

from forge.core.domain.exceptions import MCPConnectionError

logger = logging.getLogger(__name__)


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server connection."""

    name: str
    transport_type: str = "stdio"  # "stdio" | "http"
    command: Optional[List[str]] = None   # for stdio transport
    url: Optional[str] = None            # for http transport
    env: Optional[Dict[str, str]] = None


class MCPTransport(ABC):
    """Abstract MCP transport layer (JSON-RPC 2.0 framing)."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish the underlying connection."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the underlying connection cleanly."""

    @abstractmethod
    async def send(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON-RPC request and return the response dict."""


class StdioTransport(MCPTransport):
    """MCP transport over subprocess stdin/stdout using JSON-RPC 2.0.

    Each request is written as a single line of JSON followed by a newline;
    the response is read as a single line.
    """

    def __init__(
        self,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self._command = command
        self._env = env
        self._proc: Optional[asyncio.subprocess.Process] = None

    async def connect(self) -> None:
        """Spawn the MCP server subprocess."""
        merged_env = {**os.environ, **(self._env or {})}
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        logger.debug("StdioTransport: process started (pid=%s)", self._proc.pid)

    async def disconnect(self) -> None:
        """Terminate the subprocess gracefully (kill after 5 s timeout)."""
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._proc.kill()
            finally:
                self._proc = None

    async def send(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Write a JSON-RPC request and read the single-line response.

        Raises:
            MCPConnectionError: If the transport is not connected or the
                                server closes the connection unexpectedly.
        """
        if not self._proc or self._proc.stdin is None or self._proc.stdout is None:
            raise MCPConnectionError("StdioTransport is not connected")

        payload = json.dumps(request) + "\n"
        self._proc.stdin.write(payload.encode())
        await self._proc.stdin.drain()

        try:
            raw = await asyncio.wait_for(
                self._proc.stdout.readline(),
                timeout=30.0,
            )
        except asyncio.TimeoutError as exc:
            raise MCPConnectionError("MCP server response timeout") from exc

        if not raw:
            raise MCPConnectionError("MCP server closed the connection unexpectedly")

        return json.loads(raw.decode().strip())


class HTTPTransport(MCPTransport):
    """MCP transport over HTTP POST (JSON-RPC 2.0).

    Suitable for MCP servers that expose an HTTP endpoint instead of a
    subprocess interface.
    """

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self._url = url
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """Create the underlying HTTP client."""
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """POST the JSON-RPC request and return the parsed response.

        Raises:
            MCPConnectionError: If the client is not connected or an HTTP
                                error occurs.
        """
        if not self._client:
            raise MCPConnectionError("HTTPTransport is not connected")
        try:
            response = await self._client.post(self._url, json=request)
            response.raise_for_status()
            return response.json()  # type: ignore[return-value]
        except httpx.HTTPError as exc:
            raise MCPConnectionError(f"MCP HTTP error: {exc}") from exc


class MCPClient:
    """High-level MCP client that wraps a transport.

    Usage::

        client = MCPClient()
        transport = StdioTransport(command=["python", "my_mcp_server.py"])
        await client.connect(transport)
        await client.initialize()
        tools = await client.list_tools()
        result = await client.call_tool("my_tool", {"arg": "value"})
        await client.disconnect()
    """

    def __init__(self) -> None:
        self._transport: Optional[MCPTransport] = None
        self._request_id: int = 0
        self._initialized: bool = False

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _rpc(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a JSON-RPC 2.0 request dict."""
        req: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            req["params"] = params
        return req

    async def connect(self, transport: MCPTransport) -> None:
        """Connect using the given transport."""
        self._transport = transport
        await transport.connect()

    async def disconnect(self) -> None:
        """Disconnect the current transport."""
        if self._transport:
            await self._transport.disconnect()
            self._transport = None
            self._initialized = False

    async def initialize(self) -> Dict[str, Any]:
        """Send the MCP initialize handshake.

        Must be called after ``connect()`` before any other methods.

        Returns:
            The server's ``result`` dict from the initialize response.

        Raises:
            MCPConnectionError: If not connected or the handshake fails.
        """
        if not self._transport:
            raise MCPConnectionError("MCPClient is not connected to any transport")

        result = await self._transport.send(
            self._rpc(
                "initialize",
                {
                    "protocolVersion": "0.1.0",
                    "capabilities": {},
                    "clientInfo": {"name": "forge", "version": "1.0.0"},
                },
            )
        )
        if "error" in result:
            raise MCPConnectionError(
                f"MCP initialize failed: {result['error'].get('message', 'unknown error')}"
            )
        self._initialized = True
        logger.debug("MCPClient initialized: %s", result.get("result", {}))
        return result.get("result", {})

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Return the list of tools exposed by the MCP server.

        Raises:
            MCPConnectionError: If not connected.
        """
        if not self._transport:
            raise MCPConnectionError("MCPClient is not connected")

        result = await self._transport.send(self._rpc("tools/list"))
        if "error" in result:
            raise MCPConnectionError(
                f"tools/list failed: {result['error'].get('message', 'unknown')}"
            )
        return result.get("result", {}).get("tools", [])

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Invoke a named MCP tool and return its result content.

        Args:
            name: The tool name as advertised by ``list_tools()``.
            arguments: Keyword arguments to pass to the tool.

        Returns:
            The tool result content (may be a string, dict, or list).

        Raises:
            MCPConnectionError: If not connected or the tool call fails.
        """
        if not self._transport:
            raise MCPConnectionError("MCPClient is not connected")

        result = await self._transport.send(
            self._rpc(
                "tools/call",
                {"name": name, "arguments": arguments or {}},
            )
        )
        if "error" in result:
            raise MCPConnectionError(
                f"Tool '{name}' error: {result['error'].get('message', 'unknown')}"
            )
        return result.get("result", {}).get("content")

    async def __aenter__(self) -> "MCPClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()
