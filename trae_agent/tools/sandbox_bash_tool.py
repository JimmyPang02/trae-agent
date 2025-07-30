# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Sandbox-aware bash tool for isolated command execution."""

import os
from typing import override

from .bash_tool import BashTool
from .base import ToolCallArguments, ToolExecResult, ToolParameter
from .sandbox_tool import SandboxTool


class SandboxBashTool(BashTool):
    """Bash tool that executes commands in a sandbox environment when available."""
    
    name = "sandbox_bash"
    description = "Execute bash commands in a sandboxed environment when available, fallback to regular bash otherwise"
    
    def __init__(self, sandbox_tool: SandboxTool | None = None):
        super().__init__()
        self.sandbox_tool = sandbox_tool
        self.sandbox_enabled = sandbox_tool is not None
    
    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute bash commands, using sandbox if available."""
        command = arguments.get("command", "")
        
        if not command:
            return ToolExecResult(
                error="Command is required",
                error_code=1
            )
        
        # Check if sandbox is available and running
        if self.sandbox_enabled and self.sandbox_tool:
            try:
                # Check sandbox status
                status_result = await self.sandbox_tool._get_status()
                if "running" in status_result.output:
                    # Execute in sandbox
                    return await self.sandbox_tool._execute_command({
                        "command": command,
                        "working_dir": arguments.get("working_dir")
                    })
            except Exception:
                # Fall back to regular bash if sandbox fails
                pass
        
        # Fall back to regular bash execution
        return await super().execute(arguments)


class SandboxAwareBashTool(BashTool):
    """Enhanced bash tool that can automatically create and use sandbox environments."""
    
    name = "bash"
    description = "Execute bash commands with optional sandbox isolation for dependency management"
    
    parameters = BashTool.parameters + [
        ToolParameter(
            name="use_sandbox",
            type="boolean",
            description="Whether to execute the command in a sandbox environment",
            required=False
        ),
        ToolParameter(
            name="sandbox_type",
            type="string",
            description="Type of sandbox to use: 'docker' or 'venv'",
            required=False
        )
    ]
    
    def __init__(self):
        super().__init__()
        self.sandbox_tool = SandboxTool()
        self._auto_sandbox_commands = {
            # Package management commands that should trigger sandbox
            "pip install", "pip3 install",
            "npm install", "npm i", "yarn install", "yarn add",
            "conda install", "poetry install", "poetry add",
            "gem install", "bundle install",
            "go get", "go mod",
            "cargo install", "cargo add",
            "apt-get install", "apt install", "yum install", "dnf install",
            "brew install",
            # Virtual environment commands
            "python -m venv", "virtualenv", "conda create",
            "poetry env", "pipenv install"
        }
    
    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute bash commands with sandbox awareness."""
        command = arguments.get("command", "")
        use_sandbox = arguments.get("use_sandbox", False)
        sandbox_type = arguments.get("sandbox_type", "docker")
        
        if not command:
            return ToolExecResult(
                error="Command is required",
                error_code=1
            )
        
        # Auto-detect if command should use sandbox
        should_use_sandbox = use_sandbox or self._should_auto_sandbox(command)
        
        if should_use_sandbox:
            return await self._execute_with_sandbox(command, sandbox_type, arguments)
        else:
            return await super().execute(arguments)
    
    def _should_auto_sandbox(self, command: str) -> bool:
        """Determine if a command should automatically use sandbox."""
        command_lower = command.lower().strip()
        
        for trigger in self._auto_sandbox_commands:
            if command_lower.startswith(trigger):
                return True
        
        return False
    
    async def _execute_with_sandbox(self, command: str, sandbox_type: str, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute command in sandbox environment."""
        try:
            # Check if sandbox is already running
            status_result = await self.sandbox_tool._get_status()
            
            if "No sandbox environment found" in status_result.output:
                # Start sandbox
                start_result = await self.sandbox_tool._start_sandbox({
                    "workspace_path": os.getcwd(),
                    "sandbox_type": sandbox_type
                })
                
                if start_result.error:
                    # If sandbox fails to start, fall back to regular execution
                    return ToolExecResult(
                        output=f"Sandbox failed to start: {start_result.error}\nFalling back to regular execution...\n\n",
                        error=None,
                        error_code=0
                    ).merge(await super().execute(arguments))
            
            # Execute command in sandbox
            result = await self.sandbox_tool._execute_command({
                "command": command,
                "working_dir": arguments.get("working_dir")
            })
            
            # Add sandbox info to output
            sandbox_info = f"[SANDBOX] Executed in {sandbox_type} sandbox\n"
            if result.output:
                result.output = sandbox_info + result.output
            else:
                result.output = sandbox_info
            
            return result
            
        except Exception as e:
            # Fall back to regular execution if sandbox fails
            fallback_result = ToolExecResult(
                output=f"Sandbox execution failed: {str(e)}\nFalling back to regular execution...\n\n",
                error=None,
                error_code=0
            )
            regular_result = await super().execute(arguments)
            return fallback_result.merge(regular_result)
    
    async def cleanup_sandbox(self) -> ToolExecResult:
        """Clean up the sandbox environment."""
        return await self.sandbox_tool._stop_sandbox({})


# Extension for adding sandbox support to existing tools
class SandboxAwareToolMixin:
    """Mixin to add sandbox awareness to existing tools."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sandbox_tool = SandboxTool()
    
    async def execute_in_sandbox(self, command: str, sandbox_type: str = "docker", working_dir: str | None = None) -> ToolExecResult:
        """Execute a command in sandbox environment."""
        # Ensure sandbox is running
        status_result = await self.sandbox_tool._get_status()
        
        if "No sandbox environment found" in status_result.output:
            start_result = await self.sandbox_tool._start_sandbox({
                "workspace_path": working_dir or os.getcwd(),
                "sandbox_type": sandbox_type
            })
            
            if start_result.error:
                return start_result
        
        # Execute command
        return await self.sandbox_tool._execute_command({
            "command": command,
            "working_dir": working_dir
        })