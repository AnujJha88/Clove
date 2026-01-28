"""
API Key Pool Manager

Manages multiple API keys with:
- Round-robin rotation
- Rate limiting per key
- Automatic cooldown on 429 errors
- Health tracking
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from google import genai
from google.genai import types
import config


@dataclass
class KeyStats:
    """Statistics for a single API key."""
    key_id: int
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limit_hits: int = 0
    last_used: float = 0
    cooldown_until: float = 0
    is_healthy: bool = True


class APIKeyPool:
    """
    Manages a pool of API keys with intelligent rotation.

    Features:
    - Round-robin key selection
    - Per-key rate limiting
    - Automatic cooldown on errors
    - Health monitoring
    """

    def __init__(self, api_keys: list[str] = None):
        self.keys = api_keys or config.API_KEYS
        if not self.keys:
            raise ValueError("No API keys configured!")

        self.clients: dict[int, genai.Client] = {}
        self.stats: dict[int, KeyStats] = {}
        self.current_index = 0
        self._lock = asyncio.Lock()

        # Initialize clients and stats
        for i, key in enumerate(self.keys):
            self.clients[i] = genai.Client(api_key=key)
            self.stats[i] = KeyStats(key_id=i)

        print(f"[APIPool] Initialized with {len(self.keys)} API keys")

    async def get_client(self) -> tuple[genai.Client, int]:
        """
        Get the next available client using round-robin.

        Returns:
            Tuple of (client, key_id)
        """
        async with self._lock:
            attempts = 0
            while attempts < len(self.keys):
                key_id = self.current_index
                self.current_index = (self.current_index + 1) % len(self.keys)

                stats = self.stats[key_id]
                now = time.time()

                # Skip if in cooldown
                if now < stats.cooldown_until:
                    attempts += 1
                    continue

                # Skip if unhealthy (too many failures)
                if not stats.is_healthy:
                    # Try to recover after 60 seconds
                    if now - stats.last_used > 60:
                        stats.is_healthy = True
                    else:
                        attempts += 1
                        continue

                # Enforce rate limit
                time_since_last = now - stats.last_used
                if time_since_last < config.COOLDOWN_SECONDS:
                    await asyncio.sleep(config.COOLDOWN_SECONDS - time_since_last)

                stats.last_used = time.time()
                return self.clients[key_id], key_id

            # All keys exhausted, wait and retry
            min_cooldown = min(s.cooldown_until for s in self.stats.values())
            wait_time = max(0, min_cooldown - time.time()) + 1
            print(f"[APIPool] All keys in cooldown, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            return await self.get_client()

    def report_success(self, key_id: int):
        """Report successful request."""
        stats = self.stats[key_id]
        stats.total_requests += 1
        stats.successful_requests += 1

    def report_failure(self, key_id: int, error: Exception):
        """Report failed request and apply cooldown if needed."""
        stats = self.stats[key_id]
        stats.total_requests += 1
        stats.failed_requests += 1

        error_str = str(error)

        # Rate limit error - apply cooldown
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            stats.rate_limit_hits += 1
            # Exponential backoff: 10s, 20s, 40s, max 120s
            cooldown = min(10 * (2 ** min(stats.rate_limit_hits, 4)), 120)
            stats.cooldown_until = time.time() + cooldown
            print(f"[APIPool] Key {key_id} rate limited, cooldown {cooldown}s")

        # Too many consecutive failures - mark unhealthy
        if stats.failed_requests > stats.successful_requests + 5:
            stats.is_healthy = False
            print(f"[APIPool] Key {key_id} marked unhealthy")

    def get_pool_status(self) -> dict:
        """Get current status of all keys."""
        now = time.time()
        return {
            "total_keys": len(self.keys),
            "healthy_keys": sum(1 for s in self.stats.values() if s.is_healthy),
            "keys_in_cooldown": sum(1 for s in self.stats.values() if now < s.cooldown_until),
            "total_requests": sum(s.total_requests for s in self.stats.values()),
            "total_failures": sum(s.failed_requests for s in self.stats.values()),
            "total_rate_limits": sum(s.rate_limit_hits for s in self.stats.values()),
        }

    def print_status(self):
        """Print pool status."""
        status = self.get_pool_status()
        print(f"\n[APIPool Status]")
        print(f"  Keys: {status['healthy_keys']}/{status['total_keys']} healthy")
        print(f"  Requests: {status['total_requests']} total, {status['total_failures']} failed")
        print(f"  Rate limits hit: {status['total_rate_limits']}")


class LLMClient:
    """
    High-level LLM client that uses the API pool.

    Usage:
        client = LLMClient()
        response = await client.generate("Your prompt here")
    """

    def __init__(self, pool: APIKeyPool = None):
        self.pool = pool or APIKeyPool()

    async def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        model: str = None,
        max_retries: int = 3,
    ) -> str:
        """
        Generate content with automatic retry and key rotation.

        Args:
            prompt: The user prompt
            system_instruction: System instruction for the model
            model: Model name (defaults to config.MODEL_NAME)
            max_retries: Maximum retry attempts

        Returns:
            Generated text
        """
        model = model or config.MODEL_NAME

        for attempt in range(max_retries):
            client, key_id = await self.pool.get_client()

            try:
                # Build config
                gen_config = None
                if system_instruction:
                    gen_config = types.GenerateContentConfig(
                        system_instruction=system_instruction
                    )

                # Make request
                response = client.models.generate_content(
                    model=model,
                    config=gen_config,
                    contents=prompt,
                )

                self.pool.report_success(key_id)
                return response.text

            except Exception as e:
                self.pool.report_failure(key_id, e)

                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 2
                    print(f"[LLM] Retry {attempt + 1}/{max_retries} after {wait}s: {str(e)[:50]}")
                    await asyncio.sleep(wait)
                else:
                    raise

    async def generate_with_context(
        self,
        prompt: str,
        context: str,
        system_instruction: str = None,
        model: str = None,
    ) -> str:
        """Generate with additional context (e.g., from PDFs)."""
        full_prompt = f"""CONTEXT:
{context}

TASK:
{prompt}"""

        return await self.generate(
            full_prompt,
            system_instruction=system_instruction,
            model=model,
        )


# Global pool instance
_pool: APIKeyPool = None
_client: LLMClient = None


def get_pool() -> APIKeyPool:
    """Get or create the global API pool."""
    global _pool
    if _pool is None:
        _pool = APIKeyPool()
    return _pool


def get_client() -> LLMClient:
    """Get or create the global LLM client."""
    global _client
    if _client is None:
        _client = LLMClient(get_pool())
    return _client
