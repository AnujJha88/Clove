"""
File I/O Benchmark Tasks
"""

import os
import tempfile
from typing import Dict, Any


class FileIOTasks:
    """File I/O benchmark operations"""

    def __init__(self, clove_client=None):
        self.clove_client = clove_client
        self.temp_dir = tempfile.mkdtemp(prefix="clove_bench_")

    def cleanup(self):
        """Clean up temporary files"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def write_file(self, size_bytes: int, filename: str = None) -> Dict[str, Any]:
        """Write a file of specified size"""
        if filename is None:
            filename = os.path.join(self.temp_dir, f"test_{size_bytes}.bin")

        content = "x" * size_bytes

        if self.clove_client:
            # Use Clove kernel
            result = self.clove_client.write_file(filename, content)
            return {
                "success": result.get("success", False),
                "bytes_written": result.get("bytes_written", 0),
                "path": filename,
            }
        else:
            # Native Python
            with open(filename, 'w') as f:
                f.write(content)
            return {
                "success": True,
                "bytes_written": size_bytes,
                "path": filename,
            }

    def read_file(self, filename: str) -> Dict[str, Any]:
        """Read a file"""
        if self.clove_client:
            # Use Clove kernel
            result = self.clove_client.read_file(filename)
            return {
                "success": result.get("success", False),
                "size": len(result.get("content", "")),
            }
        else:
            # Native Python
            with open(filename, 'r') as f:
                content = f.read()
            return {
                "success": True,
                "size": len(content),
            }

    def write_multiple(self, size_bytes: int, count: int) -> Dict[str, Any]:
        """Write multiple files"""
        results = []
        for i in range(count):
            filename = os.path.join(self.temp_dir, f"multi_{i}_{size_bytes}.bin")
            result = self.write_file(size_bytes, filename)
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        total_bytes = sum(r.get("bytes_written", 0) for r in results)

        return {
            "success": success_count == count,
            "files_written": success_count,
            "total_bytes": total_bytes,
        }

    def read_multiple(self, sizes: list) -> Dict[str, Any]:
        """Read files of various sizes"""
        # First create the files
        files = []
        for size in sizes:
            filename = os.path.join(self.temp_dir, f"read_{size}.bin")
            self.write_file(size, filename)
            files.append(filename)

        # Now read them
        results = []
        for filename in files:
            result = self.read_file(filename)
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        total_bytes = sum(r.get("size", 0) for r in results)

        return {
            "success": success_count == len(sizes),
            "files_read": success_count,
            "total_bytes": total_bytes,
        }
