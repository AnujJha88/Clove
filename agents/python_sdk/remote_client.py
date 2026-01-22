#!/usr/bin/env python3
"""
Clove Remote Client SDK

Client library for connecting to a remote Clove kernel through a relay server.
This enables cloud agents to interact with local kernels behind NAT/firewalls.

The API is identical to CloveClient, but communication goes through
WebSocket relay instead of Unix domain sockets.

Example:
    from clove.remote_client import RemoteAgentClient

    client = RemoteAgentClient(
        relay_url="wss://relay.clove.dev",
        agent_name="cloud-worker",
        agent_token="my-token",
        target_machine="my-desktop"
    )
    client.connect()

    result = client.think("What is 2+2?")
    print(result["content"])

    client.disconnect()
"""

import json
import base64
import struct
import asyncio
import threading
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import IntEnum
from concurrent.futures import Future
import queue

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    raise ImportError("websockets library required. Run: pip install websockets")


# Protocol constants (must match kernel)
MAGIC_BYTES = 0x41474E54  # "AGNT" in hex
HEADER_SIZE = 17


class SyscallOp(IntEnum):
    """System call operations (subset used by remote clients)"""
    SYS_NOOP = 0x00
    SYS_THINK = 0x01
    SYS_EXEC = 0x02
    SYS_READ = 0x03
    SYS_WRITE = 0x04
    SYS_SPAWN = 0x10
    SYS_KILL = 0x11
    SYS_LIST = 0x12
    SYS_SEND = 0x20
    SYS_RECV = 0x21
    SYS_BROADCAST = 0x22
    SYS_REGISTER = 0x23
    SYS_STORE = 0x30
    SYS_FETCH = 0x31
    SYS_DELETE = 0x32
    SYS_KEYS = 0x33
    SYS_GET_PERMS = 0x40
    SYS_SET_PERMS = 0x41
    SYS_HTTP = 0x50
    SYS_SUBSCRIBE = 0x60
    SYS_UNSUBSCRIBE = 0x61
    SYS_POLL_EVENTS = 0x62
    SYS_EMIT = 0x63
    SYS_WORLD_CREATE = 0xA0
    SYS_WORLD_DESTROY = 0xA1
    SYS_WORLD_LIST = 0xA2
    SYS_WORLD_JOIN = 0xA3
    SYS_WORLD_LEAVE = 0xA4
    SYS_WORLD_EVENT = 0xA5
    SYS_WORLD_STATE = 0xA6
    SYS_WORLD_SNAPSHOT = 0xA7
    SYS_WORLD_RESTORE = 0xA8
    SYS_EXIT = 0xFF


@dataclass
class Message:
    """AgentOS message"""
    agent_id: int
    opcode: SyscallOp
    payload: bytes

    def serialize(self) -> bytes:
        """Serialize message to wire format"""
        header = struct.pack(
            '<IIBQ',
            MAGIC_BYTES,
            self.agent_id,
            self.opcode,
            len(self.payload)
        )
        return header + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> Optional['Message']:
        """Deserialize message from wire format"""
        if len(data) < HEADER_SIZE:
            return None

        magic, agent_id, opcode, payload_size = struct.unpack('<IIBQ', data[:HEADER_SIZE])

        if magic != MAGIC_BYTES:
            return None

        if len(data) < HEADER_SIZE + payload_size:
            return None

        payload = data[HEADER_SIZE:HEADER_SIZE + payload_size]
        return cls(agent_id=agent_id, opcode=SyscallOp(opcode), payload=payload)

    @property
    def payload_str(self) -> str:
        return self.payload.decode('utf-8', errors='replace')


class RemoteAgentClient:
    """
    Client for connecting to a remote Clove kernel via relay server.

    API is compatible with CloveClient for easy migration.
    """

    def __init__(self, relay_url: str, agent_name: str, agent_token: str,
                 target_machine: str, reconnect: bool = True):
        """
        Initialize remote agent client.

        Args:
            relay_url: WebSocket URL of relay server (e.g., ws://localhost:8765)
            agent_name: Name for this agent
            agent_token: Authentication token
            target_machine: ID of the kernel to connect to
            reconnect: Whether to auto-reconnect on disconnect
        """
        self.relay_url = relay_url
        self.agent_name = agent_name
        self.agent_token = agent_token
        self.target_machine = target_machine
        self.reconnect = reconnect

        self._ws: Optional[WebSocketClientProtocol] = None
        self._agent_id: int = 0
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # For synchronous call/response
        self._pending_responses: Dict[int, Future] = {}
        self._response_queue = queue.Queue()
        self._request_id = 0

    def connect(self) -> bool:
        """Connect to the relay server and authenticate"""
        if self._connected:
            return True

        # Start event loop in background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self._thread.start()

        # Connect asynchronously
        future = asyncio.run_coroutine_threadsafe(self._connect_async(), self._loop)
        try:
            return future.result(timeout=30)
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from the relay server"""
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._disconnect_async(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
        self._connected = False

    def _run_event_loop(self):
        """Run event loop in background thread"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect_async(self) -> bool:
        """Async connection logic"""
        try:
            self._ws = await websockets.connect(
                self.relay_url,
                ping_interval=30,
                ping_timeout=10
            )

            # Send authentication
            auth_msg = {
                "type": "agent_auth",
                "name": self.agent_name,
                "token": self.agent_token,
                "target_machine": self.target_machine
            }
            await self._ws.send(json.dumps(auth_msg))

            # Wait for auth response
            response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            data = json.loads(response)

            if data.get("type") == "auth_ok":
                self._agent_id = data.get("agent_id", 0)
                self._connected = True

                # Start message handler
                asyncio.create_task(self._message_loop())
                return True
            else:
                error = data.get("error", "Authentication failed")
                raise Exception(error)

        except Exception as e:
            self._connected = False
            if self._ws:
                await self._ws.close()
                self._ws = None
            raise

    async def _disconnect_async(self):
        """Async disconnect logic"""
        self._connected = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _message_loop(self):
        """Handle incoming messages from relay with reconnection support"""
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        base_delay = 1.0

        while self._connected or (self.reconnect and reconnect_attempts < max_reconnect_attempts):
            try:
                if self._ws is None:
                    break

                async for message in self._ws:
                    reconnect_attempts = 0  # Reset on successful message
                    try:
                        data = json.loads(message)
                        await self._handle_message(data)
                    except json.JSONDecodeError as e:
                        print(f"Invalid JSON from relay: {e}")
                    except Exception as e:
                        print(f"Error handling message: {e}")

            except websockets.ConnectionClosed as e:
                self._connected = False
                if self.reconnect and reconnect_attempts < max_reconnect_attempts:
                    reconnect_attempts += 1
                    delay = base_delay * (2 ** (reconnect_attempts - 1))  # Exponential backoff
                    print(f"Connection closed (code={e.code}), reconnecting in {delay:.1f}s... (attempt {reconnect_attempts}/{max_reconnect_attempts})")
                    await asyncio.sleep(delay)
                    try:
                        if await self._connect_async():
                            continue
                    except Exception as re:
                        print(f"Reconnection failed: {re}")
                else:
                    print(f"Connection closed: {e}")
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                print(f"Message loop error: {e}")
                break

        self._connected = False

    async def _handle_message(self, data: dict):
        """Handle a message from relay"""
        msg_type = data.get("type")

        if msg_type == "response":
            # Syscall response from kernel
            opcode = data.get("opcode", 0)
            payload_b64 = data.get("payload", "")
            payload = base64.b64decode(payload_b64) if payload_b64 else b""

            # Put response in queue for synchronous callers
            self._response_queue.put(Message(
                agent_id=self._agent_id,
                opcode=SyscallOp(opcode),
                payload=payload
            ))

        elif msg_type == "kernel_disconnected":
            self._connected = False
            print(f"Kernel disconnected: {data.get('machine_id')}")

        elif msg_type == "error":
            print(f"Relay error: {data.get('error')}")

    def call(self, opcode: SyscallOp, payload: bytes | str = b'') -> Optional[Message]:
        """Send a syscall and wait for response"""
        if not self._connected or not self._loop:
            return None

        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        # Clear response queue
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except queue.Empty:
                break

        # Send syscall
        future = asyncio.run_coroutine_threadsafe(
            self._send_syscall(opcode, payload),
            self._loop
        )

        try:
            future.result(timeout=5)
        except Exception as e:
            print(f"Failed to send syscall: {e}")
            return None

        # Wait for response
        try:
            response = self._response_queue.get(timeout=60)
            return response
        except queue.Empty:
            print("Timeout waiting for response")
            return None

    async def _send_syscall(self, opcode: SyscallOp, payload: bytes):
        """Send a syscall to kernel via relay"""
        if not self._ws:
            return

        msg = {
            "type": "syscall",
            "opcode": int(opcode),
            "payload": base64.b64encode(payload).decode() if payload else ""
        }
        await self._ws.send(json.dumps(msg))

    # =========================================================================
    # High-level API (compatible with AgentOSClient)
    # =========================================================================

    def echo(self, message: str) -> Optional[str]:
        """Echo a message (for testing)"""
        response = self.call(SyscallOp.SYS_NOOP, message)
        return response.payload_str if response else None

    def think(self, prompt: str,
              image: bytes = None,
              image_mime_type: str = "image/jpeg",
              system_instruction: str = None,
              thinking_level: str = None,
              temperature: float = None,
              model: str = None) -> dict:
        """Send a prompt to the LLM via kernel"""
        payload = {"prompt": prompt}

        if image:
            payload["image"] = {
                "data": base64.b64encode(image).decode(),
                "mime_type": image_mime_type
            }
        if system_instruction:
            payload["system_instruction"] = system_instruction
        if thinking_level:
            payload["thinking_level"] = thinking_level
        if temperature is not None:
            payload["temperature"] = temperature
        if model:
            payload["model"] = model

        response = self.call(SyscallOp.SYS_THINK, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": True, "content": response.payload_str}
        return {"success": False, "content": "", "error": "No response"}

    def exec(self, command: str, cwd: str = None, timeout: int = 30) -> dict:
        """Execute a shell command"""
        payload = {"command": command, "timeout": timeout}
        if cwd:
            payload["cwd"] = cwd

        response = self.call(SyscallOp.SYS_EXEC, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def read_file(self, path: str) -> dict:
        """Read a file's contents"""
        response = self.call(SyscallOp.SYS_READ, json.dumps({"path": path}))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def write_file(self, path: str, content: str, mode: str = "write") -> dict:
        """Write content to a file"""
        payload = {"path": path, "content": content, "mode": mode}
        response = self.call(SyscallOp.SYS_WRITE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def spawn(self, name: str, script: str, sandboxed: bool = True,
              network: bool = False, limits: dict = None) -> Optional[dict]:
        """Spawn a new agent"""
        payload = {"name": name, "script": script, "sandboxed": sandboxed, "network": network}
        if limits:
            payload["limits"] = limits

        response = self.call(SyscallOp.SYS_SPAWN, json.dumps(payload))
        if response:
            return json.loads(response.payload_str)
        return None

    def kill(self, name: str = None, agent_id: int = None) -> bool:
        """Kill a running agent"""
        payload = {}
        if name:
            payload["name"] = name
        elif agent_id:
            payload["id"] = agent_id
        else:
            return False

        response = self.call(SyscallOp.SYS_KILL, json.dumps(payload))
        if response:
            result = json.loads(response.payload_str)
            return result.get("killed", False)
        return False

    def list_agents(self) -> list:
        """List all running agents"""
        response = self.call(SyscallOp.SYS_LIST)
        if response:
            return json.loads(response.payload_str)
        return []

    def register_name(self, name: str) -> dict:
        """Register this agent with a name"""
        response = self.call(SyscallOp.SYS_REGISTER, json.dumps({"name": name}))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def send_message(self, message: dict, to: int = None, to_name: str = None) -> dict:
        """Send a message to another agent"""
        payload = {"message": message}
        if to is not None:
            payload["to"] = to
        if to_name is not None:
            payload["to_name"] = to_name

        response = self.call(SyscallOp.SYS_SEND, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def recv_messages(self, max_messages: int = 10) -> dict:
        """Receive pending messages"""
        response = self.call(SyscallOp.SYS_RECV, json.dumps({"max": max_messages}))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "messages": [], "error": response.payload_str}
        return {"success": False, "messages": [], "error": "No response"}

    def http(self, url: str, method: str = "GET", headers: dict = None,
             body: str = None, timeout: int = 30) -> dict:
        """Make an HTTP request"""
        payload = {"url": url, "method": method, "timeout": timeout}
        if headers:
            payload["headers"] = headers
        if body:
            payload["body"] = body

        response = self.call(SyscallOp.SYS_HTTP, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def store(self, key: str, value, scope: str = "global", ttl: int = None) -> dict:
        """Store a key-value pair"""
        payload = {"key": key, "value": value, "scope": scope}
        if ttl is not None:
            payload["ttl"] = ttl

        response = self.call(SyscallOp.SYS_STORE, json.dumps(payload))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def fetch(self, key: str) -> dict:
        """Fetch a value"""
        response = self.call(SyscallOp.SYS_FETCH, json.dumps({"key": key}))
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def get_permissions(self) -> dict:
        """Get this agent's permissions"""
        response = self.call(SyscallOp.SYS_GET_PERMS, "{}")
        if response:
            try:
                return json.loads(response.payload_str)
            except json.JSONDecodeError:
                return {"success": False, "error": response.payload_str}
        return {"success": False, "error": "No response"}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# Convenience function
def connect_remote(relay_url: str, agent_name: str, agent_token: str,
                  target_machine: str) -> RemoteAgentClient:
    """Create and connect a remote client"""
    client = RemoteAgentClient(
        relay_url=relay_url,
        agent_name=agent_name,
        agent_token=agent_token,
        target_machine=target_machine
    )
    if not client.connect():
        raise ConnectionError(f"Failed to connect to relay at {relay_url}")
    return client


if __name__ == '__main__':
    print("Clove Remote Client SDK")
    print("=======================")
    print()
    print("Usage:")
    print("  from clove.remote_client import RemoteAgentClient")
    print()
    print("  client = RemoteAgentClient(")
    print('      relay_url="ws://localhost:8765",')
    print('      agent_name="my-agent",')
    print('      agent_token="my-token",')
    print('      target_machine="my-pc"')
    print("  )")
    print("  client.connect()")
    print()
    print('  result = client.think("Hello!")')
    print("  print(result)")
    print()
    print("  client.disconnect()")
