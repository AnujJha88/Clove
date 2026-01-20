#!/usr/bin/env python3
"""
AgentOS Relay Server - REST API

Provides HTTP API endpoints for:
- Fleet management (machines list, status)
- Token management (create, revoke)
- Agent deployment and management
"""

import asyncio
import json
import logging
import base64
from datetime import datetime
from typing import Dict, Any, Optional
from aiohttp import web

from auth import get_auth_manager
from router import get_router
from fleet import get_fleet_manager
from tokens import get_token_store

logger = logging.getLogger(__name__)


class RelayAPI:
    """REST API for the AgentOS Relay Server."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8766):
        self.host = host
        self.port = port
        self.app = web.Application(middlewares=[self._error_middleware])
        self._setup_routes()
        self._runner = None

    def _setup_routes(self):
        """Set up API routes."""
        self.app.router.add_get('/api/v1/status', self.get_status)
        self.app.router.add_get('/api/v1/health', self.health_check)

        # Machine endpoints
        self.app.router.add_get('/api/v1/machines', self.list_machines)
        self.app.router.add_get('/api/v1/machines/{machine_id}', self.get_machine)
        self.app.router.add_post('/api/v1/machines', self.register_machine)
        self.app.router.add_delete('/api/v1/machines/{machine_id}', self.remove_machine)

        # Agent endpoints
        self.app.router.add_get('/api/v1/agents', self.list_agents)
        self.app.router.add_post('/api/v1/agents/deploy', self.deploy_agent)
        self.app.router.add_post('/api/v1/agents/{agent_id}/stop', self.stop_agent)

        # Token endpoints
        self.app.router.add_get('/api/v1/tokens', self.list_tokens)
        self.app.router.add_post('/api/v1/tokens/machine', self.create_machine_token)
        self.app.router.add_post('/api/v1/tokens/agent', self.create_agent_token)
        self.app.router.add_delete('/api/v1/tokens/{token_id}', self.revoke_token)

    @web.middleware
    async def _error_middleware(self, request, handler):
        """Handle errors and return JSON responses."""
        try:
            return await handler(request)
        except web.HTTPException as e:
            return web.json_response({
                'error': e.reason,
                'status': e.status
            }, status=e.status)
        except Exception as e:
            logger.error(f"API error: {e}", exc_info=True)
            return web.json_response({
                'error': str(e),
                'status': 500
            }, status=500)

    # =========================================================================
    # Status Endpoints
    # =========================================================================

    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

    async def get_status(self, request: web.Request) -> web.Response:
        """Get overall relay server status."""
        router = get_router()
        fleet = get_fleet_manager()

        status = {
            'server': 'running',
            'timestamp': datetime.now().isoformat(),
            **router.get_status(),
            'fleet': fleet.get_summary()
        }

        return web.json_response(status)

    # =========================================================================
    # Machine Endpoints
    # =========================================================================

    async def list_machines(self, request: web.Request) -> web.Response:
        """List all registered machines."""
        fleet = get_fleet_manager()
        router = get_router()

        machines = []
        for mid, info in fleet.list_machines().items():
            # Check if machine is connected
            is_connected = router.is_kernel_connected(mid)
            machines.append({
                'machine_id': mid,
                'provider': info.get('provider', 'unknown'),
                'status': 'connected' if is_connected else 'disconnected',
                'ip_address': info.get('ip_address', ''),
                'created_at': info.get('created_at', ''),
                'last_seen': info.get('last_seen', ''),
                'metadata': info.get('metadata', {})
            })

        return web.json_response({'machines': machines})

    async def get_machine(self, request: web.Request) -> web.Response:
        """Get details of a specific machine."""
        machine_id = request.match_info['machine_id']
        fleet = get_fleet_manager()
        router = get_router()

        machine = fleet.get_machine(machine_id)
        if not machine:
            raise web.HTTPNotFound(reason=f'Machine not found: {machine_id}')

        is_connected = router.is_kernel_connected(machine_id)

        return web.json_response({
            'machine_id': machine_id,
            'provider': machine.get('provider', 'unknown'),
            'status': 'connected' if is_connected else 'disconnected',
            'ip_address': machine.get('ip_address', ''),
            'created_at': machine.get('created_at', ''),
            'last_seen': machine.get('last_seen', ''),
            'metadata': machine.get('metadata', {})
        })

    async def register_machine(self, request: web.Request) -> web.Response:
        """Register a new machine."""
        data = await request.json()

        machine_id = data.get('machine_id')
        if not machine_id:
            raise web.HTTPBadRequest(reason='machine_id is required')

        fleet = get_fleet_manager()
        token_store = get_token_store()

        # Create machine token
        token = token_store.create_machine_token(machine_id, data.get('name', ''))

        # Register in fleet
        fleet.register_machine(
            machine_id=machine_id,
            provider=data.get('provider', 'unknown'),
            ip_address=data.get('ip_address', ''),
            metadata=data.get('metadata', {})
        )

        return web.json_response({
            'machine_id': machine_id,
            'token': token,
            'created_at': datetime.now().isoformat()
        }, status=201)

    async def remove_machine(self, request: web.Request) -> web.Response:
        """Remove a machine from the fleet."""
        machine_id = request.match_info['machine_id']
        fleet = get_fleet_manager()

        if not fleet.remove_machine(machine_id):
            raise web.HTTPNotFound(reason=f'Machine not found: {machine_id}')

        return web.json_response({'removed': machine_id})

    # =========================================================================
    # Agent Endpoints
    # =========================================================================

    async def list_agents(self, request: web.Request) -> web.Response:
        """List running agents."""
        machine_id = request.query.get('machine_id')
        router = get_router()

        if machine_id:
            agents = router.list_remote_agents_for_kernel(machine_id)
        else:
            agents = [
                {
                    'agent_id': a.agent_id,
                    'agent_name': a.agent_name,
                    'target_machine': a.target_machine,
                    'connected_at': a.connected_at.isoformat(),
                    'syscalls_sent': a.syscalls_sent,
                    'responses_received': a.responses_received,
                    'status': 'running'
                }
                for a in router.remote_agents.values()
            ]

        return web.json_response({'agents': agents})

    async def deploy_agent(self, request: web.Request) -> web.Response:
        """Deploy an agent to a machine."""
        data = await request.json()

        machine_id = data.get('machine_id')
        script_content = data.get('script_content')
        script_name = data.get('script_name', 'agent.py')

        if not machine_id:
            raise web.HTTPBadRequest(reason='machine_id is required')
        if not script_content:
            raise web.HTTPBadRequest(reason='script_content is required')

        router = get_router()

        # Check if kernel is connected
        if not router.is_kernel_connected(machine_id):
            raise web.HTTPBadRequest(reason=f'Kernel {machine_id} not connected')

        # Get kernel connection
        kernel = router.get_kernel(machine_id)
        if not kernel:
            raise web.HTTPNotFound(reason=f'Kernel not found: {machine_id}')

        # Send deploy command to kernel
        deploy_msg = {
            'type': 'deploy_agent',
            'script_name': script_name,
            'script_content': base64.b64encode(script_content.encode()).decode(),
            'args': data.get('args', [])
        }

        try:
            await kernel.ws.send(json.dumps(deploy_msg))

            # Wait for response (with timeout)
            # Note: In production, this should use a proper request-response mechanism
            await asyncio.sleep(0.5)

            return web.json_response({
                'status': 'deploying',
                'machine_id': machine_id,
                'script_name': script_name
            }, status=202)

        except Exception as e:
            raise web.HTTPInternalServerError(reason=f'Failed to deploy: {e}')

    async def stop_agent(self, request: web.Request) -> web.Response:
        """Stop a running agent."""
        agent_id = int(request.match_info['agent_id'])
        data = await request.json()
        machine_id = data.get('machine_id')

        if not machine_id:
            raise web.HTTPBadRequest(reason='machine_id is required')

        router = get_router()
        kernel = router.get_kernel(machine_id)

        if not kernel:
            raise web.HTTPNotFound(reason=f'Kernel not found: {machine_id}')

        # Send stop command to kernel
        stop_msg = {
            'type': 'stop_agent',
            'agent_id': agent_id
        }

        try:
            await kernel.ws.send(json.dumps(stop_msg))
            return web.json_response({'stopped': agent_id})
        except Exception as e:
            raise web.HTTPInternalServerError(reason=f'Failed to stop agent: {e}')

    # =========================================================================
    # Token Endpoints
    # =========================================================================

    async def list_tokens(self, request: web.Request) -> web.Response:
        """List all tokens (without exposing actual token values)."""
        token_store = get_token_store()
        tokens = token_store.list_tokens()

        return web.json_response({'tokens': tokens})

    async def create_machine_token(self, request: web.Request) -> web.Response:
        """Create a token for a machine."""
        data = await request.json()

        machine_id = data.get('machine_id')
        if not machine_id:
            raise web.HTTPBadRequest(reason='machine_id is required')

        token_store = get_token_store()
        token = token_store.create_machine_token(
            machine_id=machine_id,
            name=data.get('name', '')
        )

        # Also register in auth manager
        auth = get_auth_manager()
        auth.register_machine(machine_id, token)

        return web.json_response({
            'token': token,
            'machine_id': machine_id,
            'type': 'machine'
        }, status=201)

    async def create_agent_token(self, request: web.Request) -> web.Response:
        """Create a token for an agent."""
        data = await request.json()

        target_machine = data.get('target_machine')
        if not target_machine:
            raise web.HTTPBadRequest(reason='target_machine is required')

        token_store = get_token_store()
        auth = get_auth_manager()

        expires_hours = data.get('expires_hours', 24)
        token = auth.create_agent_token(
            agent_name=data.get('name', 'api-agent'),
            target_machine=target_machine,
            expires_in_hours=expires_hours
        )

        # Store token metadata
        token_id = token_store.store_agent_token(
            token=token,
            target_machine=target_machine,
            name=data.get('name', ''),
            expires_hours=expires_hours
        )

        return web.json_response({
            'token': token,
            'id': token_id,
            'target_machine': target_machine,
            'type': 'agent'
        }, status=201)

    async def revoke_token(self, request: web.Request) -> web.Response:
        """Revoke a token."""
        token_id = request.match_info['token_id']
        token_store = get_token_store()

        if not token_store.revoke_token(token_id):
            raise web.HTTPNotFound(reason=f'Token not found: {token_id}')

        return web.json_response({'revoked': token_id})

    # =========================================================================
    # Server Lifecycle
    # =========================================================================

    async def start(self):
        """Start the API server."""
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        logger.info(f"REST API server started on http://{self.host}:{self.port}")

    async def stop(self):
        """Stop the API server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("REST API server stopped")


# Singleton instance
_api: Optional[RelayAPI] = None


def get_api(host: str = "0.0.0.0", port: int = 8766) -> RelayAPI:
    """Get or create the global API instance."""
    global _api
    if _api is None:
        _api = RelayAPI(host, port)
    return _api
