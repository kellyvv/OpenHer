"""Sandboxed shell command executor for OpenClaw SKILL execution."""

import asyncio


async def execute_shell(command: str, timeout: int = 30) -> dict:
    """Execute a shell command in sandbox, return stdout/stderr.

    Args:
        command: Shell command to execute.
        timeout: Maximum execution time in seconds.

    Returns:
        dict with keys: success, stdout, stderr, returncode.
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()  # 防止 zombie
        return {
            "success": False,
            "stdout": "",
            "stderr": "command timed out",
            "returncode": -1,
        }
    return {
        "success": proc.returncode == 0,
        "stdout": stdout.decode("utf-8", errors="replace").strip(),
        "stderr": stderr.decode("utf-8", errors="replace").strip(),
        "returncode": proc.returncode,
    }
