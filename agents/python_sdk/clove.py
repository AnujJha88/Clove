"""
Backwards compatibility shim for Clove -> AgentOS transition.
Re-exports everything from agentos module.
"""
from agentos import *

__all__ = ['CloveClient', 'AgentOSClient', 'connect']
