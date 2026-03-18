"""
ToolRegistry — Central registry for atomic skill tools.

Each tool is a named async function with an OpenAI-compatible JSON Schema
definition. Skills mount tools by name via SKILL.md `tools:` field.

ModalitySkillEngine uses the registry to:
  1. Convert mounted tool names → OpenAI function calling format
  2. Execute tool calls returned by LLM
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class Tool:
    """A registered atomic tool."""
    name: str                          # Unique ID, e.g. "generate_photo"
    description: str                   # Shown to LLM in function schema
    parameters: dict                   # JSON Schema for function parameters
    handler: Callable[..., Awaitable[dict]]  # async (**kwargs) -> dict


class ToolRegistry:
    """Global registry of atomic tools available to skills."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Overwrites if name already exists."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def to_openai_tools(self, names: list[str]) -> list[dict]:
        """Convert specified tool names to OpenAI function calling format.

        Args:
            names: List of tool names to include (from SKILL.md `tools:` field).

        Returns:
            List of OpenAI tool definitions, ready for `tools=` parameter.
        """
        result = []
        for name in names:
            tool = self._tools.get(name)
            if tool:
                result.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                })
        return result

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict:
        """Execute a tool by name with parsed arguments.

        Args:
            name: Tool name.
            arguments: Parsed arguments dict from LLM function call.

        Returns:
            Tool result dict.

        Raises:
            ValueError: If tool not found.
        """
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        return await tool.handler(**arguments)

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def __repr__(self) -> str:
        return f"ToolRegistry({list(self._tools.keys())})"
