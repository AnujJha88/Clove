#!/usr/bin/env python3
"""
AgentOS Tunnel Client

Python service that connects the kernel to a relay server, enabling
remote agents to connect through NAT/firewalls.

This runs as a subprocess of the kernel and communicates via stdin/stdout
using JSON-RPC style messages.

Protocol (stdin/stdout JSON lines):
    Request:  {"id": 1, "method": "connect", "params": {...}}
    Response: {"id": 1, "result": {...}} or {"id": 1, "error": {...}}

    Async events (from relay):
    {"event": "agent_connected", "data": {...}}
    {"event": "syscall", "data": {...}}
"""

import asyncio
import json
import sys
import os
import signal
import base64
import struct
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from dotenv import load_dotenv

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    print(json.dumps({"error": "websockets library not installed"}), flush=True)
    sys.exit(1)

# Protocol constants (must match kernel)
MAGIC_BYTES = 0x41474E54  # "AGNT" in hex
HEADER_SIZE = 17


@dataclass
class TunnelConfig:
    """Tunnel configuration"""
    relay_url: str = ""
    machine_id: str = ""
    token: str = ""
    reconnect_interval: int = 5
    heartbeat_interval: int = 30


@dataclass
class RemoteAgent:
    """Information about a connected remote agent"""
    agent_id: int
    name: str
    connected_at: datetime = field(default_factory=datetime.now)


class TunnelClient:
    """WebSocket client that connects kernel to relay server"""

    def __init__(self):
        self.config = TunnelConfig()
        self._ws: Optional[WebSocketClientProtocol] = None
        self._connected = False
        self._running = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._remote_agents: Dict[int, RemoteAgent] = {}

        # Callback for syscalls from remote agents
        self._syscall_handler: Optional[Callable] = None

        # Pending responses for request-response pattern
        self._pending_responses: Dict[int, asyncio.Future] = {}
        self._next_request_id = 1

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    async def configure(self, relay_url: str, machine_id: str, token: str,
                       reconnect_interval: int = 5):
        """Configure tunnel settings"""
        self.config.relay_url = relay_url
        self.config.machine_id = machine_id
        self.config.token = token
        self.config.reconnect_interval = reconnect_interval

    async def connect(self) -> bool:
        """Connect to the relay server"""
        if not self.config.relay_url:
            return False

        try:
            self._ws = await websockets.connect(
                self.config.relay_url,
                ping_interval=30,
                ping_timeout=10
            )

            # Send authentication
            auth_msg = {
                "type": "kernel_auth",
                "machine_id": self.config.machine_id,
                "token": self.config.token
            }
            await self._ws.send(json.dumps(auth_msg))

            # Wait for auth response
            response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            data = json.loads(response)

            if data.get("type") == "auth_ok":
                self._connected = True
                self._running = True

                # Start message handler
                asyncio.create_task(self._message_loop())

                # Start heartbeat
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                return True
            else:
                error = data.get("error", "Unknown error")
                raise Exception(f"Auth failed: {error}")

        except Exception as e:
            self._connected = False
            if self._ws:
                await self._ws.close()
                self._ws = None
            raise

    async def disconnect(self):
        """Disconnect from relay server"""
        self._running = False
        self._connected = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._remote_agents.clear()

    async def _message_loop(self):
        """Handle incoming messages from relay"""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    await self._handle_relay_message(data)
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    self._emit_event("error", {"message": str(e)})
        except websockets.ConnectionClosed:
            self._connected = False
            self._emit_event("disconnected", {})
            if self._running:
                # Schedule reconnect
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())
        except Exception as e:
            self._connected = False
            self._emit_event("error", {"message": str(e)})

    async def _handle_relay_message(self, data: dict):
        """Handle a message from the relay server"""
        msg_type = data.get("type")

        if msg_type == "agent_connected":
            # New remote agent connected
            agent_id = data.get("agent_id")
            name = data.get("name", "unknown")
            self._remote_agents[agent_id] = RemoteAgent(agent_id=agent_id, name=name)
            self._emit_event("agent_connected", {
                "agent_id": agent_id,
                "name": name
            })

        elif msg_type == "agent_disconnected":
            # Remote agent disconnected
            agent_id = data.get("agent_id")
            if agent_id in self._remote_agents:
                del self._remote_agents[agent_id]
            self._emit_event("agent_disconnected", {
                "agent_id": agent_id
            })

        elif msg_type == "syscall":
            # Syscall from remote agent - forward to kernel
            agent_id = data.get("agent_id")
            opcode = data.get("opcode", 0)
            payload_b64 = data.get("payload", "")
            payload = base64.b64decode(payload_b64) if payload_b64 else b""

            self._emit_event("syscall", {
                "agent_id": agent_id,
                "opcode": opcode,
                "payload": payload_b64
            })

        elif msg_type == "remote_list":
            # Response to list_remotes request
            agents = data.get("agents", [])
            self._emit_event("remote_list", {"agents": agents})

        elif msg_type == "pong":
            pass  # Heartbeat response

    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self._running and self._connected:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                if self._ws:
                    await self._ws.send(json.dumps({"type": "ping"}))
            except Exception:
                break

    async def _reconnect_loop(self):
        """Try to reconnect after disconnection"""
        while self._running and not self._connected:
            try:
                await asyncio.sleep(self.config.reconnect_interval)
                self._emit_event("reconnecting", {})
                await self.connect()
                self._emit_event("reconnected", {})
            except Exception as e:
                self._emit_event("reconnect_failed", {"error": str(e)})

    async def send_response(self, agent_id: int, opcode: int, payload: bytes):
        """Send a syscall response back to a remote agent"""
        if not self.is_connected:
            return False

        msg = {
            "type": "response",
            "agent_id": agent_id,
            "opcode": opcode,
            "payload": base64.b64encode(payload).decode() if payload else ""
        }

        try:
            await self._ws.send(json.dumps(msg))
            return True
        except Exception:
            return False

    async def list_remote_agents(self) -> list:
        """Request list of connected remote agents"""
        if not self.is_connected:
            return []

        await self._ws.send(json.dumps({"type": "list_remotes"}))
        # Response will come via event
        return list(self._remote_agents.values())

    def get_status(self) -> dict:
        """Get tunnel status"""
        return {
            "connected": self._connected,
            "relay_url": self.config.relay_url,
            "machine_id": self.config.machine_id,
            "remote_agents": len(self._remote_agents)
        }

    def _emit_event(self, event_type: str, data: dict):
        """Emit an event to stdout for kernel to read"""
        print(json.dumps({"event": event_type, "data": data}), flush=True)


class TunnelService:
    """JSON-RPC style service for kernel communication"""

    def __init__(self):
        self.client = TunnelClient()
        self._running = False

    async def handle_request(self, request: dict) -> dict:
        """Handle a JSON-RPC style request"""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        try:
            if method == "configure":
                await self.client.configure(
                    relay_url=params.get("relay_url", ""),
                    machine_id=params.get("machine_id", ""),
                    token=params.get("token", ""),
                    reconnect_interval=params.get("reconnect_interval", 5)
                )
                return {"id": req_id, "result": {"success": True}}

            elif method == "connect":
                await self.client.connect()
                return {"id": req_id, "result": {"success": True}}

            elif method == "disconnect":
                await self.client.disconnect()
                return {"id": req_id, "result": {"success": True}}

            elif method == "status":
                status = self.client.get_status()
                return {"id": req_id, "result": status}

            elif method == "list_remotes":
                agents = await self.client.list_remote_agents()
                return {"id": req_id, "result": {
                    "agents": [
                        {"agent_id": a.agent_id, "name": a.name}
                        for a in agents
                    ]
                }}

            elif method == "send_response":
                # Forward syscall response to remote agent
                success = await self.client.send_response(
                    agent_id=params.get("agent_id"),
                    opcode=params.get("opcode", 0),
                    payload=base64.b64decode(params.get("payload", ""))
                )
                return {"id": req_id, "result": {"success": success}}

            elif method == "shutdown":
                self._running = False
                return {"id": req_id, "result": {"success": True}}

            else:
                return {"id": req_id, "error": {"message": f"Unknown method: {method}"}}

        except Exception as e:
            return {"id": req_id, "error": {"message": str(e)}}

    async def run(self):
        """Main service loop - read from stdin, write to stdout"""
        self._running = True
        loop = asyncio.get_event_loop()

        # Read from stdin asynchronously
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break

                line = line.decode().strip()
                if not line:
                    continue

                request = json.loads(line)
                response = await self.handle_request(request)
                print(json.dumps(response), flush=True)

            except json.JSONDecodeError:
                print(json.dumps({"error": {"message": "Invalid JSON"}}), flush=True)
            except Exception as e:
                print(json.dumps({"error": {"message": str(e)}}), flush=True)

        # Cleanup
        await self.client.disconnect()


async def main():
    """Main entry point"""
    load_dotenv()

    service = TunnelService()

    # Handle signals
    def shutdown_handler():
        service._running = False

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    # Send ready message
    print(json.dumps({"event": "ready", "data": {}}), flush=True)

    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
