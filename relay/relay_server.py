#!/usr/bin/env python3
"""
AgentOS Relay Server

WebSocket-based relay server that enables cloud agents to connect to
local AgentOS kernels through NAT/firewall.

Architecture:
    [Remote Agent] <--> [Relay Server] <--> [Local Kernel]

Both the kernel and remote agents connect outbound to the relay server,
which routes messages between them.

Usage:
    python relay_server.py --port 8765

Environment Variables:
    RELAY_HOST: Host to bind to (default: 0.0.0.0)
    RELAY_PORT: Port to listen on (default: 8765)
    RELAY_DEV_MODE: Enable development mode (auto-register machines)
    MACHINE_TOKEN_<id>: Pre-registered machine tokens
"""

import asyncio
import json
import base64
import logging
import argparse
import os
import signal
from typing import Optional
from dotenv import load_dotenv

try:
    import websockets
    from websockets.server import WebSocketServerProtocol, serve
except ImportError:
    print("Error: websockets library not installed.")
    print("Run: pip install websockets")
    exit(1)

from auth import get_auth_manager, AuthManager
from router import get_router, MessageRouter

# Try to import API module (optional)
try:
    from api import get_api
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class RelayServer:
    """AgentOS Relay Server"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.auth: AuthManager = get_auth_manager()
        self.router: MessageRouter = get_router()
        self._server = None
        self._running = False

    async def handle_connection(self, websocket: WebSocketServerProtocol):
        """Handle a new WebSocket connection"""
        remote_addr = websocket.remote_address
        logger.info(f"New connection from {remote_addr}")

        connection_type = None  # "kernel" or "agent"

        try:
            # Wait for authentication message
            auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            auth_data = json.loads(auth_msg)

            msg_type = auth_data.get("type")

            if msg_type == "kernel_auth":
                connection_type = "kernel"
                await self._handle_kernel_auth(websocket, auth_data)
            elif msg_type == "agent_auth":
                connection_type = "agent"
                await self._handle_agent_auth(websocket, auth_data)
            else:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": f"Unknown auth type: {msg_type}"
                }))
                return

        except asyncio.TimeoutError:
            logger.warning(f"Auth timeout for {remote_addr}")
            await websocket.send(json.dumps({
                "type": "error",
                "error": "Authentication timeout"
            }))
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from {remote_addr}")
            await websocket.send(json.dumps({
                "type": "error",
                "error": "Invalid JSON"
            }))
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            # Clean up on disconnect
            if connection_type == "kernel":
                await self.router.unregister_kernel(websocket)
            elif connection_type == "agent":
                await self.router.unregister_remote_agent(websocket)
            logger.info(f"Connection closed: {remote_addr}")

    async def _handle_kernel_auth(self, websocket: WebSocketServerProtocol,
                                  auth_data: dict):
        """Handle kernel authentication and message loop"""
        machine_id = auth_data.get("machine_id", "")
        token = auth_data.get("token", "")

        if not machine_id:
            await websocket.send(json.dumps({
                "type": "auth_error",
                "error": "machine_id required"
            }))
            return

        # Validate credentials
        if not self.auth.validate_machine(machine_id, token):
            logger.warning(f"Auth failed for kernel: {machine_id}")
            await websocket.send(json.dumps({
                "type": "auth_error",
                "error": "Invalid credentials"
            }))
            return

        # Register kernel
        await self.router.register_kernel(websocket, machine_id)

        # Send auth success
        await websocket.send(json.dumps({
            "type": "auth_ok",
            "machine_id": machine_id
        }))

        logger.info(f"Kernel authenticated: {machine_id}")

        # Message loop for kernel
        async for message in websocket:
            try:
                data = json.loads(message)
                await self._handle_kernel_message(websocket, machine_id, data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from kernel {machine_id}")
            except Exception as e:
                logger.error(f"Error handling kernel message: {e}")

    async def _handle_kernel_message(self, websocket: WebSocketServerProtocol,
                                    machine_id: str, data: dict):
        """Handle a message from a kernel"""
        msg_type = data.get("type")

        if msg_type == "response":
            # Forward syscall response to remote agent
            agent_id = data.get("agent_id")
            opcode = data.get("opcode", 0)
            payload_b64 = data.get("payload", "")
            payload = base64.b64decode(payload_b64) if payload_b64 else b""

            await self.router.route_response_to_agent(
                websocket, agent_id, opcode, payload
            )

        elif msg_type == "list_remotes":
            # List connected remote agents
            agents = self.router.list_remote_agents_for_kernel(machine_id)
            await websocket.send(json.dumps({
                "type": "remote_list",
                "agents": agents
            }))

        elif msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))

        else:
            logger.warning(f"Unknown message type from kernel: {msg_type}")

    async def _handle_agent_auth(self, websocket: WebSocketServerProtocol,
                                auth_data: dict):
        """Handle remote agent authentication and message loop"""
        agent_name = auth_data.get("name", "unnamed")
        token = auth_data.get("token", "")
        target_machine = auth_data.get("target_machine", "")

        if not target_machine:
            await websocket.send(json.dumps({
                "type": "auth_error",
                "error": "target_machine required"
            }))
            return

        # Validate token
        agent_token = self.auth.validate_agent_token(token, target_machine)
        if not agent_token:
            logger.warning(f"Auth failed for agent: {agent_name}")
            await websocket.send(json.dumps({
                "type": "auth_error",
                "error": "Invalid token or target machine"
            }))
            return

        # Check if kernel is connected
        if not self.router.is_kernel_connected(target_machine):
            await websocket.send(json.dumps({
                "type": "auth_error",
                "error": f"Kernel {target_machine} not connected"
            }))
            return

        # Register remote agent
        agent_id = await self.router.register_remote_agent(
            websocket, agent_name, target_machine
        )

        if agent_id is None:
            await websocket.send(json.dumps({
                "type": "auth_error",
                "error": "Failed to register agent"
            }))
            return

        # Send auth success with assigned agent ID
        await websocket.send(json.dumps({
            "type": "auth_ok",
            "agent_id": agent_id,
            "target_machine": target_machine
        }))

        logger.info(f"Remote agent authenticated: {agent_name} (id={agent_id})")

        # Message loop for remote agent
        async for message in websocket:
            try:
                data = json.loads(message)
                await self._handle_agent_message(websocket, agent_id, data)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from agent {agent_name}")
            except Exception as e:
                logger.error(f"Error handling agent message: {e}")

    async def _handle_agent_message(self, websocket: WebSocketServerProtocol,
                                   agent_id: int, data: dict):
        """Handle a message from a remote agent"""
        msg_type = data.get("type")

        if msg_type == "syscall":
            # Forward syscall to kernel
            opcode = data.get("opcode", 0)
            payload_b64 = data.get("payload", "")
            payload = base64.b64decode(payload_b64) if payload_b64 else b""

            success = await self.router.route_syscall_to_kernel(
                websocket, opcode, payload
            )

            if not success:
                # Send error response back to agent
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": "Failed to route syscall to kernel"
                }))

        elif msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))

        else:
            logger.warning(f"Unknown message type from agent: {msg_type}")

    async def start(self):
        """Start the relay server"""
        self._running = True

        logger.info(f"Starting AgentOS Relay Server on {self.host}:{self.port}")

        self._server = await serve(
            self.handle_connection,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10
        )

        logger.info("Relay server started")

        # Wait for server to close
        await self._server.wait_closed()

    async def stop(self):
        """Stop the relay server"""
        if self._server:
            self._running = False
            self._server.close()
            await self._server.wait_closed()
            logger.info("Relay server stopped")

    def get_status(self) -> dict:
        """Get server status"""
        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            **self.router.get_status()
        }


async def main():
    """Main entry point"""
    # Load environment variables
    load_dotenv()

    parser = argparse.ArgumentParser(description="AgentOS Relay Server")
    parser.add_argument("--host", default=os.environ.get("RELAY_HOST", "0.0.0.0"),
                       help="Host to bind to")
    parser.add_argument("--port", type=int,
                       default=int(os.environ.get("RELAY_PORT", "8765")),
                       help="WebSocket port to listen on")
    parser.add_argument("--api-port", type=int,
                       default=int(os.environ.get("RELAY_API_PORT", "8766")),
                       help="REST API port to listen on")
    parser.add_argument("--no-api", action="store_true",
                       help="Disable REST API server")
    parser.add_argument("--dev", action="store_true",
                       help="Enable development mode")
    args = parser.parse_args()

    if args.dev:
        os.environ["RELAY_DEV_MODE"] = "true"
        logger.info("Development mode enabled - auto-registering machines")

    server = RelayServer(host=args.host, port=args.port)

    # Handle shutdown gracefully
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def shutdown_handler():
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    # Start WebSocket server
    server_task = asyncio.create_task(server.start())

    # Start REST API server (if available and not disabled)
    api = None
    if API_AVAILABLE and not args.no_api:
        api = get_api(args.host, args.api_port)
        await api.start()
        logger.info(f"REST API available at http://{args.host}:{args.api_port}")
    elif not API_AVAILABLE and not args.no_api:
        logger.warning("REST API not available (aiohttp not installed)")

    # Wait for shutdown
    await stop_event.wait()

    # Stop servers
    if api:
        await api.stop()
    await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
