"""Base agent class for CLOVE demos.

Provides a standard pattern for agent scripts that receive work via IPC,
process it, and send results back.
"""
from __future__ import annotations

import sys
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from .utils import ensure_sdk_on_path, log, read_json, write_json

ensure_sdk_on_path()

if TYPE_CHECKING:
    from clove_sdk import CloveClient


class BaseAgent(ABC):
    """Base class for demo agents.

    Subclasses implement the `process` method to handle incoming work.
    The run loop handles connection, message receiving, and error handling.

    Example:
        class MyAgent(BaseAgent):
            name = "my-agent"

            def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
                # Do work
                return {"result": "done"}

        if __name__ == "__main__":
            MyAgent().run()
    """

    name: str = "agent"

    def __init__(self, socket_path: Optional[str] = None):
        """Initialize the agent.

        Args:
            socket_path: Override default socket path
        """
        self.socket_path = socket_path
        self.client: Optional["CloveClient"] = None
        self.run_dir: Optional[Path] = None

    @abstractmethod
    def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming work payload.

        Args:
            payload: Message payload from orchestrator

        Returns:
            Result dict to send back
        """
        raise NotImplementedError

    def setup(self) -> None:
        """Optional setup hook called before main loop."""
        pass

    def teardown(self) -> None:
        """Optional teardown hook called after main loop."""
        pass

    def log(self, level: str, msg: str) -> None:
        """Log a message with this agent's name."""
        log(self.name, level, msg)

    def info(self, msg: str) -> None:
        """Log an INFO message."""
        self.log("INFO", msg)

    def error(self, msg: str) -> None:
        """Log an ERROR message."""
        self.log("ERROR", msg)

    def warn(self, msg: str) -> None:
        """Log a WARNING message."""
        self.log("WARNING", msg)

    def save_artifact(self, name: str, data: Dict[str, Any]) -> Path:
        """Save an artifact JSON file.

        Args:
            name: Artifact filename (without .json extension)
            data: Data to save

        Returns:
            Path to saved artifact
        """
        if not self.run_dir:
            raise RuntimeError("run_dir not set")

        path = self.run_dir / "artifacts" / f"{name}.json"
        write_json(path, data)
        return path

    def load_artifact(self, name: str) -> Dict[str, Any]:
        """Load an artifact JSON file.

        Args:
            name: Artifact filename (without .json extension)

        Returns:
            Loaded data or empty dict if not found
        """
        if not self.run_dir:
            raise RuntimeError("run_dir not set")

        path = self.run_dir / "artifacts" / f"{name}.json"
        return read_json(path)

    def run(self) -> None:
        """Main agent run loop.

        Connects to kernel, receives messages, processes them, and sends results.
        """
        from clove_sdk import CloveClient

        self.info(f"Starting {self.name}")

        try:
            # Connect to kernel
            if self.socket_path:
                self.client = CloveClient(self.socket_path)
            else:
                self.client = CloveClient()

            if not self.client.connect():
                self.error("Failed to connect to kernel")
                sys.exit(1)

            self.info(f"Connected as agent {self.client.agent_id}")

            # Register name
            self.client.register_name(self.name)

            # Setup hook
            self.setup()

            # Main message loop
            while True:
                result = self.client.recv_messages()
                messages = result.messages if hasattr(result, 'messages') else result.get("messages", [])

                for msg in messages:
                    payload = msg.message if hasattr(msg, 'message') else msg.get("message", {})
                    if not payload:
                        continue

                    msg_type = payload.get("type", "")

                    # Handle shutdown
                    if msg_type == "shutdown":
                        self.info("Received shutdown signal")
                        return

                    # Handle run_dir setup
                    if "run_dir" in payload and not self.run_dir:
                        self.run_dir = Path(payload["run_dir"])

                    # Process the message
                    try:
                        response = self.process(payload)
                        if response:
                            self.client.send_message(0, response)  # Send to orchestrator
                    except Exception as e:
                        self.error(f"Error processing message: {e}")
                        traceback.print_exc()
                        self.client.send_message(0, {
                            "type": "error",
                            "agent": self.name,
                            "error": str(e),
                        })

        except KeyboardInterrupt:
            self.info("Interrupted")
        except Exception as e:
            self.error(f"Fatal error: {e}")
            traceback.print_exc()
            sys.exit(1)
        finally:
            self.teardown()
            if self.client:
                self.client.disconnect()
            self.info("Shutdown complete")
