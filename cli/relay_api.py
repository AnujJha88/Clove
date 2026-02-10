#!/usr/bin/env python3
"""
AgentOS Relay REST API Client

Provides a Python client for the Relay Server's REST API.
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class MachineInfo:
    """Information about a deployed machine."""
    machine_id: str
    provider: str  # docker, aws, gcp
    status: str  # running, stopped, pending
    ip_address: str
    created_at: str
    last_seen: Optional[str] = None
    metadata: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict) -> 'MachineInfo':
        return cls(
            machine_id=data.get('machine_id', ''),
            provider=data.get('provider', 'unknown'),
            status=data.get('status', 'unknown'),
            ip_address=data.get('ip_address', ''),
            created_at=data.get('created_at', ''),
            last_seen=data.get('last_seen'),
            metadata=data.get('metadata', {})
        )


@dataclass
class AgentInfo:
    """Information about a running agent."""
    agent_id: int
    agent_name: str
    target_machine: str
    status: str
    connected_at: str
    syscalls_sent: int = 0
    responses_received: int = 0

    @classmethod
    def from_dict(cls, data: Dict) -> 'AgentInfo':
        return cls(
            agent_id=data.get('agent_id', 0),
            agent_name=data.get('agent_name', 'unknown'),
            target_machine=data.get('target_machine', ''),
            status=data.get('status', 'unknown'),
            connected_at=data.get('connected_at', ''),
            syscalls_sent=data.get('syscalls_sent', 0),
            responses_received=data.get('responses_received', 0)
        )


class RelayAPIError(Exception):
    """Error from Relay API."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class RelayAPIClient:
    """Client for AgentOS Relay REST API."""

    def __init__(self, api_url: str, api_token: str = ""):
        self.api_url = api_url.rstrip('/')
        self.api_token = api_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {}
            if self.api_token:
                headers['Authorization'] = f'Bearer {self.api_token}'
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, endpoint: str,
                       data: Dict = None) -> Dict[str, Any]:
        """Make an API request."""
        session = await self._get_session()
        url = f"{self.api_url}{endpoint}"

        try:
            async with session.request(method, url, json=data) as resp:
                body = await resp.json()
                if resp.status >= 400:
                    raise RelayAPIError(
                        body.get('error', 'Unknown error'),
                        resp.status
                    )
                return body
        except aiohttp.ClientError as e:
            raise RelayAPIError(f"Connection error: {e}")

    # =========================================================================
    # Fleet Management
    # =========================================================================

    async def get_status(self) -> Dict[str, Any]:
        """Get overall relay server status."""
        return await self._request('GET', '/api/v1/status')

    async def list_machines(self) -> List[MachineInfo]:
        """List all registered machines."""
        data = await self._request('GET', '/api/v1/machines')
        return [MachineInfo.from_dict(m) for m in data.get('machines', [])]

    async def get_machine(self, machine_id: str) -> MachineInfo:
        """Get details of a specific machine."""
        data = await self._request('GET', f'/api/v1/machines/{machine_id}')
        return MachineInfo.from_dict(data)

    async def register_machine(self, machine_id: str, provider: str,
                               ip_address: str = "",
                               metadata: Dict = None) -> Dict[str, Any]:
        """Register a new machine."""
        return await self._request('POST', '/api/v1/machines', {
            'machine_id': machine_id,
            'provider': provider,
            'ip_address': ip_address,
            'metadata': metadata or {}
        })

    async def remove_machine(self, machine_id: str) -> bool:
        """Remove a machine from the fleet."""
        await self._request('DELETE', f'/api/v1/machines/{machine_id}')
        return True

    # =========================================================================
    # Agent Management
    # =========================================================================

    async def list_agents(self, machine_id: str = None) -> List[AgentInfo]:
        """List running agents, optionally filtered by machine."""
        endpoint = '/api/v1/agents'
        if machine_id:
            endpoint += f'?machine_id={machine_id}'
        data = await self._request('GET', endpoint)
        return [AgentInfo.from_dict(a) for a in data.get('agents', [])]

    async def deploy_agent(self, script_path: str, machine_id: str,
                          args: List[str] = None) -> Dict[str, Any]:
        """Deploy an agent to a machine."""
        # Read the script content
        with open(script_path) as f:
            script_content = f.read()

        return await self._request('POST', '/api/v1/agents/deploy', {
            'machine_id': machine_id,
            'script_content': script_content,
            'script_name': script_path,
            'args': args or []
        })

    async def stop_agent(self, machine_id: str, agent_id: int) -> bool:
        """Stop a running agent."""
        await self._request('POST', f'/api/v1/agents/{agent_id}/stop', {
            'machine_id': machine_id
        })
        return True

    # =========================================================================
    # Token Management
    # =========================================================================

    async def create_machine_token(self, machine_id: str,
                                   name: str = "") -> Dict[str, Any]:
        """Create a token for a machine."""
        return await self._request('POST', '/api/v1/tokens/machine', {
            'machine_id': machine_id,
            'name': name
        })

    async def create_agent_token(self, target_machine: str,
                                 name: str = "",
                                 expires_hours: int = 24) -> Dict[str, Any]:
        """Create a token for an agent."""
        return await self._request('POST', '/api/v1/tokens/agent', {
            'target_machine': target_machine,
            'name': name,
            'expires_hours': expires_hours
        })

    async def list_tokens(self) -> List[Dict[str, Any]]:
        """List all tokens."""
        data = await self._request('GET', '/api/v1/tokens')
        return data.get('tokens', [])

    async def revoke_token(self, token_id: str) -> bool:
        """Revoke a token."""
        await self._request('DELETE', f'/api/v1/tokens/{token_id}')
        return True


def run_async(coro):
    """Helper to run async functions from sync code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class SyncRelayAPIClient:
    """Synchronous wrapper for RelayAPIClient."""

    def __init__(self, api_url: str, api_token: str = ""):
        self.api_url = api_url
        self.api_token = api_token

    def _run(self, coro):
        """Run an async coroutine synchronously."""
        async def _wrapper():
            client = RelayAPIClient(self.api_url, self.api_token)
            try:
                return await coro(client)
            finally:
                await client.close()
        return run_async(_wrapper())

    def get_status(self) -> Dict[str, Any]:
        return self._run(lambda c: c.get_status())

    def list_machines(self) -> List[MachineInfo]:
        return self._run(lambda c: c.list_machines())

    def get_machine(self, machine_id: str) -> MachineInfo:
        return self._run(lambda c: c.get_machine(machine_id))

    def register_machine(self, machine_id: str, provider: str,
                        ip_address: str = "", metadata: Dict = None) -> Dict:
        return self._run(lambda c: c.register_machine(
            machine_id, provider, ip_address, metadata
        ))

    def remove_machine(self, machine_id: str) -> bool:
        return self._run(lambda c: c.remove_machine(machine_id))

    def list_agents(self, machine_id: str = None) -> List[AgentInfo]:
        return self._run(lambda c: c.list_agents(machine_id))

    def deploy_agent(self, script_path: str, machine_id: str,
                    args: List[str] = None) -> Dict:
        return self._run(lambda c: c.deploy_agent(script_path, machine_id, args))

    def create_machine_token(self, machine_id: str, name: str = "") -> Dict:
        return self._run(lambda c: c.create_machine_token(machine_id, name))

    def create_agent_token(self, target_machine: str, name: str = "",
                          expires_hours: int = 24) -> Dict:
        return self._run(lambda c: c.create_agent_token(
            target_machine, name, expires_hours
        ))

    def list_tokens(self) -> List[Dict]:
        return self._run(lambda c: c.list_tokens())

    def revoke_token(self, token_id: str) -> bool:
        return self._run(lambda c: c.revoke_token(token_id))
