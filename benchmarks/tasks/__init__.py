"""
Benchmark Task Implementations

Each task can be run either natively (direct Python) or through Clove.
"""

from .file_io import FileIOTasks
from .compute import ComputeTasks
from .agent import AgentTasks
from .ipc import IPCTasks

__all__ = ['FileIOTasks', 'ComputeTasks', 'AgentTasks', 'IPCTasks']
