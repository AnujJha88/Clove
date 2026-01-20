#!/usr/bin/env python3
"""
AgentOS Fleet Client

High-level Python client for managing AgentOS fleets.
Combines relay API access with agent execution.

Usage:
    from fleet_client import FleetClient

    fleet = FleetClient(relay_url="http://localhost:8766")

    # List all machines
    machines = fleet.list_machines()

    # Deploy an agent
    fleet.deploy_agent("my_agent.py", machine_id="docker-kernel-abc123")

    # Run agent on all machines
    fleet.run_on_all("health_check.py")
"""

import os
import sys
import asyncio
import aiohttp
import json
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Machine:
    """Represents a machine in the fleet."""
    machine_id: str
    provider: str
    status: str
    ip_address: str = ""
    created_at: str = ""
    last_seen: str = ""
    metadata: Dict[str, Any] = None

    def is_connected(self) -> bool:
        return self.status == "connected"


@dataclass
class Agent:
    """Represents a running agent."""
    agent_id: int
    agent_name: str
    target_machine: str
    status: str
    syscalls_sent: int = 0


class FleetClientError(Exception):
    """Fleet client error."""
    pass


class FleetClient:
    """Client for managing AgentOS fleets."""

    def __init__(self, relay_url: str = None, api_token: str = None):
        """
        Initialize the fleet client.

        Args:
            relay_url: Base URL for the relay REST API (e.g., "http://localhost:8766")
            api_token: Optional authentication token
        """
        self.relay_url = relay_url or os.environ.get("RELAY_API_URL", "http://localhost:8766")
        self.api_token = api_token or os.environ.get("AGENTOS_API_TOKEN", "")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make an API request."""
        session = await self._get_session()
        url = f"{self.relay_url.rstrip('/')}{endpoint}"

        try:
            async with session.request(method, url, json=data) as resp:
                body = await resp.json()
                if resp.status >= 400:
                    raise FleetClientError(body.get("error", f"HTTP {resp.status}"))
                return body
        except aiohttp.ClientError as e:
            raise FleetClientError(f"Connection error: {e}")

    # =========================================================================
    # Machine Operations
    # =========================================================================

    async def list_machines(self) -> List[Machine]:
        """List all machines in the fleet."""
        data = await self._request("GET", "/api/v1/machines")
        return [Machine(**m) for m in data.get("machines", [])]

    async def get_machine(self, machine_id: str) -> Machine:
        """Get details of a specific machine."""
        data = await self._request("GET", f"/api/v1/machines/{machine_id}")
        return Machine(**data)

    async def get_connected_machines(self) -> List[Machine]:
        """Get all connected machines."""
        machines = await self.list_machines()
        return [m for m in machines if m.is_connected()]

    # =========================================================================
    # Agent Operations
    # =========================================================================

    async def list_agents(self, machine_id: str = None) -> List[Agent]:
        """List running agents."""
        endpoint = "/api/v1/agents"
        if machine_id:
            endpoint += f"?machine_id={machine_id}"
        data = await self._request("GET", endpoint)
        return [Agent(**a) for a in data.get("agents", [])]

    async def deploy_agent(self, script_path: str, machine_id: str,
                          args: List[str] = None) -> Dict[str, Any]:
        """
        Deploy an agent to a machine.

        Args:
            script_path: Path to the agent script
            machine_id: Target machine ID
            args: Optional arguments for the agent

        Returns:
            Deployment result dict
        """
        path = Path(script_path)
        if not path.exists():
            raise FleetClientError(f"Script not found: {script_path}")

        script_content = path.read_text()

        return await self._request("POST", "/api/v1/agents/deploy", {
            "machine_id": machine_id,
            "script_content": script_content,
            "script_name": path.name,
            "args": args or []
        })

    async def run_on_all(self, script_path: str, args: List[str] = None,
                        filter_fn: Callable[[Machine], bool] = None) -> List[Dict]:
        """
        Run an agent on all connected machines.

        Args:
            script_path: Path to the agent script
            args: Optional arguments
            filter_fn: Optional filter function for machines

        Returns:
            List of deployment results
        """
        machines = await self.get_connected_machines()

        if filter_fn:
            machines = [m for m in machines if filter_fn(m)]

        if not machines:
            raise FleetClientError("No machines available")

        results = []
        for machine in machines:
            try:
                result = await self.deploy_agent(script_path, machine.machine_id, args)
                results.append({"machine_id": machine.machine_id, "status": "deployed", **result})
            except FleetClientError as e:
                results.append({"machine_id": machine.machine_id, "status": "failed", "error": str(e)})

        return results

    async def stop_agent(self, machine_id: str, agent_id: int) -> bool:
        """Stop a running agent."""
        await self._request("POST", f"/api/v1/agents/{agent_id}/stop", {
            "machine_id": machine_id
        })
        return True

    # =========================================================================
    # Fleet Status
    # =========================================================================

    async def get_status(self) -> Dict[str, Any]:
        """Get overall fleet status."""
        return await self._request("GET", "/api/v1/status")

    async def health_check(self) -> bool:
        """Check if the relay server is healthy."""
        try:
            data = await self._request("GET", "/api/v1/health")
            return data.get("status") == "healthy"
        except FleetClientError:
            return False


# Synchronous wrapper
class SyncFleetClient:
    """Synchronous wrapper for FleetClient."""

    def __init__(self, relay_url: str = None, api_token: str = None):
        self.relay_url = relay_url
        self.api_token = api_token

    def _run(self, coro):
        """Run an async coroutine synchronously."""
        async def _wrapper():
            client = FleetClient(self.relay_url, self.api_token)
            try:
                return await coro(client)
            finally:
                await client.close()

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_wrapper())
        finally:
            loop.close()

    def list_machines(self) -> List[Machine]:
        return self._run(lambda c: c.list_machines())

    def get_machine(self, machine_id: str) -> Machine:
        return self._run(lambda c: c.get_machine(machine_id))

    def get_connected_machines(self) -> List[Machine]:
        return self._run(lambda c: c.get_connected_machines())

    def list_agents(self, machine_id: str = None) -> List[Agent]:
        return self._run(lambda c: c.list_agents(machine_id))

    def deploy_agent(self, script_path: str, machine_id: str,
                    args: List[str] = None) -> Dict[str, Any]:
        return self._run(lambda c: c.deploy_agent(script_path, machine_id, args))

    def run_on_all(self, script_path: str, args: List[str] = None) -> List[Dict]:
        return self._run(lambda c: c.run_on_all(script_path, args))

    def stop_agent(self, machine_id: str, agent_id: int) -> bool:
        return self._run(lambda c: c.stop_agent(machine_id, agent_id))

    def get_status(self) -> Dict[str, Any]:
        return self._run(lambda c: c.get_status())

    def health_check(self) -> bool:
        return self._run(lambda c: c.health_check())
