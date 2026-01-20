#!/usr/bin/env python3
"""
AgentOS Relay Server - Message Router

Routes messages between kernels and remote agents.
"""

import asyncio
import json
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Set, Tuple, Any
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


@dataclass
class KernelConnection:
    """Represents a connected kernel"""
    ws: WebSocketServerProtocol
    machine_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    local_agent_ids: Set[int] = field(default_factory=set)
    # Stats
    messages_received: int = 0
    messages_sent: int = 0


@dataclass
class RemoteAgentConnection:
    """Represents a connected remote agent"""
    ws: WebSocketServerProtocol
    agent_id: int  # Assigned by relay (1000+)
    agent_name: str
    target_machine: str
    connected_at: datetime = field(default_factory=datetime.now)
    # Stats
    syscalls_sent: int = 0
    responses_received: int = 0


class MessageRouter:
    """Routes messages between kernels and remote agents"""

    def __init__(self):
        # machine_id -> KernelConnection
        self.kernels: Dict[str, KernelConnection] = {}

        # (machine_id, agent_id) -> RemoteAgentConnection
        self.remote_agents: Dict[Tuple[str, int], RemoteAgentConnection] = {}

        # WebSocket -> connection info (for reverse lookup on disconnect)
        self.ws_to_kernel: Dict[WebSocketServerProtocol, str] = {}
        self.ws_to_agent: Dict[WebSocketServerProtocol, Tuple[str, int]] = {}

        # Next agent ID for remote agents (starts at 1000)
        self._next_agent_id = 1000
        self._agent_id_lock = asyncio.Lock()

    async def _get_next_agent_id(self) -> int:
        """Get the next available agent ID"""
        async with self._agent_id_lock:
            agent_id = self._next_agent_id
            self._next_agent_id += 1
            return agent_id

    # =========================================================================
    # Kernel Management
    # =========================================================================

    async def register_kernel(self, ws: WebSocketServerProtocol,
                            machine_id: str) -> bool:
        """Register a kernel connection"""
        if machine_id in self.kernels:
            # Kernel already connected - replace connection
            old_conn = self.kernels[machine_id]
            if old_conn.ws in self.ws_to_kernel:
                del self.ws_to_kernel[old_conn.ws]
            logger.warning(f"Replacing existing kernel connection for {machine_id}")

        conn = KernelConnection(ws=ws, machine_id=machine_id)
        self.kernels[machine_id] = conn
        self.ws_to_kernel[ws] = machine_id

        logger.info(f"Kernel registered: {machine_id}")
        return True

    async def unregister_kernel(self, ws: WebSocketServerProtocol):
        """Unregister a kernel on disconnect"""
        if ws not in self.ws_to_kernel:
            return

        machine_id = self.ws_to_kernel[ws]
        del self.ws_to_kernel[ws]

        if machine_id in self.kernels:
            del self.kernels[machine_id]

        # Notify all remote agents connected to this kernel
        agents_to_remove = [
            key for key in self.remote_agents
            if key[0] == machine_id
        ]

        for key in agents_to_remove:
            agent_conn = self.remote_agents[key]
            try:
                await agent_conn.ws.send(json.dumps({
                    "type": "kernel_disconnected",
                    "machine_id": machine_id
                }))
            except Exception:
                pass  # Agent might be disconnected too

        logger.info(f"Kernel unregistered: {machine_id}")

    def get_kernel(self, machine_id: str) -> Optional[KernelConnection]:
        """Get a kernel connection by machine ID"""
        return self.kernels.get(machine_id)

    def is_kernel_connected(self, machine_id: str) -> bool:
        """Check if a kernel is connected"""
        return machine_id in self.kernels

    # =========================================================================
    # Remote Agent Management
    # =========================================================================

    async def register_remote_agent(self, ws: WebSocketServerProtocol,
                                   agent_name: str,
                                   target_machine: str) -> Optional[int]:
        """Register a remote agent and assign an ID"""
        if not self.is_kernel_connected(target_machine):
            logger.warning(f"Cannot register agent {agent_name}: "
                          f"kernel {target_machine} not connected")
            return None

        agent_id = await self._get_next_agent_id()
        key = (target_machine, agent_id)

        conn = RemoteAgentConnection(
            ws=ws,
            agent_id=agent_id,
            agent_name=agent_name,
            target_machine=target_machine
        )

        self.remote_agents[key] = conn
        self.ws_to_agent[ws] = key

        # Notify kernel about new remote agent
        kernel = self.kernels[target_machine]
        try:
            await kernel.ws.send(json.dumps({
                "type": "agent_connected",
                "agent_id": agent_id,
                "name": agent_name
            }))
        except Exception as e:
            logger.error(f"Failed to notify kernel of agent connection: {e}")

        logger.info(f"Remote agent registered: {agent_name} (id={agent_id}) "
                   f"-> {target_machine}")
        return agent_id

    async def unregister_remote_agent(self, ws: WebSocketServerProtocol):
        """Unregister a remote agent on disconnect"""
        if ws not in self.ws_to_agent:
            return

        key = self.ws_to_agent[ws]
        del self.ws_to_agent[ws]

        if key in self.remote_agents:
            conn = self.remote_agents[key]
            del self.remote_agents[key]

            # Notify kernel about agent disconnect
            machine_id, agent_id = key
            if machine_id in self.kernels:
                try:
                    await self.kernels[machine_id].ws.send(json.dumps({
                        "type": "agent_disconnected",
                        "agent_id": agent_id,
                        "name": conn.agent_name
                    }))
                except Exception:
                    pass  # Kernel might be disconnected

            logger.info(f"Remote agent unregistered: {conn.agent_name} (id={agent_id})")

    def get_remote_agent(self, machine_id: str,
                        agent_id: int) -> Optional[RemoteAgentConnection]:
        """Get a remote agent connection"""
        return self.remote_agents.get((machine_id, agent_id))

    # =========================================================================
    # Message Routing
    # =========================================================================

    async def route_syscall_to_kernel(self, agent_ws: WebSocketServerProtocol,
                                     opcode: int, payload: bytes) -> bool:
        """Route a syscall from remote agent to kernel"""
        if agent_ws not in self.ws_to_agent:
            logger.error("Syscall from unregistered agent")
            return False

        machine_id, agent_id = self.ws_to_agent[agent_ws]
        agent_conn = self.remote_agents.get((machine_id, agent_id))

        if not agent_conn:
            return False

        kernel = self.kernels.get(machine_id)
        if not kernel:
            logger.error(f"Kernel {machine_id} not connected")
            return False

        # Forward to kernel
        msg = {
            "type": "syscall",
            "agent_id": agent_id,
            "opcode": opcode,
            "payload": base64.b64encode(payload).decode() if payload else ""
        }

        try:
            await kernel.ws.send(json.dumps(msg))
            kernel.messages_received += 1
            agent_conn.syscalls_sent += 1
            return True
        except Exception as e:
            logger.error(f"Failed to forward syscall to kernel: {e}")
            return False

    async def route_response_to_agent(self, kernel_ws: WebSocketServerProtocol,
                                     agent_id: int, opcode: int,
                                     payload: bytes) -> bool:
        """Route a response from kernel to remote agent"""
        if kernel_ws not in self.ws_to_kernel:
            logger.error("Response from unregistered kernel")
            return False

        machine_id = self.ws_to_kernel[kernel_ws]
        agent_conn = self.remote_agents.get((machine_id, agent_id))

        if not agent_conn:
            logger.warning(f"Response for unknown agent {agent_id}")
            return False

        # Forward to agent
        msg = {
            "type": "response",
            "opcode": opcode,
            "payload": base64.b64encode(payload).decode() if payload else ""
        }

        try:
            await agent_conn.ws.send(json.dumps(msg))
            agent_conn.responses_received += 1
            return True
        except Exception as e:
            logger.error(f"Failed to forward response to agent: {e}")
            return False

    # =========================================================================
    # Status & Stats
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get router status for monitoring"""
        return {
            "kernels_connected": len(self.kernels),
            "remote_agents_connected": len(self.remote_agents),
            "kernels": [
                {
                    "machine_id": k.machine_id,
                    "connected_at": k.connected_at.isoformat(),
                    "messages_received": k.messages_received,
                    "messages_sent": k.messages_sent,
                    "remote_agents": len([
                        a for a in self.remote_agents.values()
                        if a.target_machine == k.machine_id
                    ])
                }
                for k in self.kernels.values()
            ],
            "agents": [
                {
                    "agent_id": a.agent_id,
                    "agent_name": a.agent_name,
                    "target_machine": a.target_machine,
                    "connected_at": a.connected_at.isoformat(),
                    "syscalls_sent": a.syscalls_sent,
                    "responses_received": a.responses_received
                }
                for a in self.remote_agents.values()
            ]
        }

    def list_remote_agents_for_kernel(self, machine_id: str) -> list:
        """List all remote agents connected to a kernel"""
        return [
            {
                "agent_id": conn.agent_id,
                "agent_name": conn.agent_name,
                "connected_at": conn.connected_at.isoformat()
            }
            for key, conn in self.remote_agents.items()
            if key[0] == machine_id
        ]


# Singleton instance
_router: Optional[MessageRouter] = None


def get_router() -> MessageRouter:
    """Get the global router instance"""
    global _router
    if _router is None:
        _router = MessageRouter()
    return _router
