"""
Compute Benchmark Tasks

CPU-bound tasks for measuring computational overhead.
"""

from typing import Dict, Any


class ComputeTasks:
    """Compute benchmark operations"""

    def __init__(self, clove_client=None):
        self.clove_client = clove_client

    def fibonacci(self, n: int) -> Dict[str, Any]:
        """Compute Fibonacci number (recursive with memoization)"""
        if self.clove_client:
            # Execute via Clove shell
            code = f'''
import sys
def fib(n, memo={{}}):
    if n in memo: return memo[n]
    if n <= 1: return n
    memo[n] = fib(n-1, memo) + fib(n-2, memo)
    return memo[n]
print(fib({n}))
'''
            result = self.clove_client.exec(f"python3 -c '{code}'")
            if result.get("success"):
                try:
                    value = int(result.get("stdout", "0").strip())
                    return {"success": True, "result": value}
                except ValueError:
                    return {"success": False, "error": "Invalid output"}
            return {"success": False, "error": result.get("stderr", "Unknown error")}
        else:
            # Native Python
            def fib(n, memo={}):
                if n in memo:
                    return memo[n]
                if n <= 1:
                    return n
                memo[n] = fib(n - 1, memo) + fib(n - 2, memo)
                return memo[n]

            result = fib(n)
            return {"success": True, "result": result}

    def prime_sieve(self, limit: int) -> Dict[str, Any]:
        """Sieve of Eratosthenes"""
        if self.clove_client:
            # Execute via Clove shell
            code = f'''
def sieve(limit):
    is_prime = [True] * (limit + 1)
    is_prime[0] = is_prime[1] = False
    for i in range(2, int(limit**0.5) + 1):
        if is_prime[i]:
            for j in range(i*i, limit + 1, i):
                is_prime[j] = False
    return sum(is_prime)
print(sieve({limit}))
'''
            result = self.clove_client.exec(f"python3 -c '{code}'")
            if result.get("success"):
                try:
                    count = int(result.get("stdout", "0").strip())
                    return {"success": True, "prime_count": count}
                except ValueError:
                    return {"success": False, "error": "Invalid output"}
            return {"success": False, "error": result.get("stderr", "Unknown error")}
        else:
            # Native Python
            def sieve(limit):
                is_prime = [True] * (limit + 1)
                is_prime[0] = is_prime[1] = False
                for i in range(2, int(limit ** 0.5) + 1):
                    if is_prime[i]:
                        for j in range(i * i, limit + 1, i):
                            is_prime[j] = False
                return sum(is_prime)

            count = sieve(limit)
            return {"success": True, "prime_count": count}

    def matrix_multiply(self, size: int) -> Dict[str, Any]:
        """Matrix multiplication (NxN)"""
        if self.clove_client:
            code = f'''
import random
n = {size}
A = [[random.random() for _ in range(n)] for _ in range(n)]
B = [[random.random() for _ in range(n)] for _ in range(n)]
C = [[sum(A[i][k]*B[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
print(len(C))
'''
            result = self.clove_client.exec(f"python3 -c '{code}'")
            return {
                "success": result.get("success", False),
                "matrix_size": size,
            }
        else:
            import random
            n = size
            A = [[random.random() for _ in range(n)] for _ in range(n)]
            B = [[random.random() for _ in range(n)] for _ in range(n)]
            C = [[sum(A[i][k] * B[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
            return {
                "success": True,
                "matrix_size": len(C),
            }

    def string_operations(self, iterations: int) -> Dict[str, Any]:
        """String manipulation benchmark"""
        if self.clove_client:
            code = f'''
s = ""
for i in range({iterations}):
    s += str(i)
    if i % 100 == 0:
        s = s.replace("1", "one")
print(len(s))
'''
            result = self.clove_client.exec(f"python3 -c '{code}'")
            if result.get("success"):
                try:
                    length = int(result.get("stdout", "0").strip())
                    return {"success": True, "string_length": length}
                except ValueError:
                    return {"success": False, "error": "Invalid output"}
            return {"success": False, "error": result.get("stderr", "Unknown error")}
        else:
            s = ""
            for i in range(iterations):
                s += str(i)
                if i % 100 == 0:
                    s = s.replace("1", "one")
            return {"success": True, "string_length": len(s)}
