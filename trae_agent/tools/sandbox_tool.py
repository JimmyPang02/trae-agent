# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Sandbox tool for isolated execution environments."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, override

from .base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter


class SandboxEnvironment:
    """Manages a sandboxed execution environment using containers or isolated processes."""
    
    def __init__(self, workspace_path: str, sandbox_type: str = "docker"):
        self.workspace_path = Path(workspace_path).resolve()
        self.sandbox_type = sandbox_type
        self.container_id: Optional[str] = None
        self.temp_dir: Optional[str] = None
        self.is_running = False
        
    async def start(self) -> None:
        """Start the sandbox environment."""
        if self.is_running:
            return
            
        if self.sandbox_type == "docker":
            await self._start_docker_sandbox()
        elif self.sandbox_type == "venv":
            await self._start_venv_sandbox()
        else:
            raise ToolError(f"Unsupported sandbox type: {self.sandbox_type}")
            
        self.is_running = True
    
    async def stop(self) -> None:
        """Stop the sandbox environment."""
        if not self.is_running:
            return
            
        if self.sandbox_type == "docker" and self.container_id:
            await self._stop_docker_sandbox()
        elif self.sandbox_type == "venv" and self.temp_dir:
            await self._stop_venv_sandbox()
            
        self.is_running = False
    
    async def execute_command(self, command: str, cwd: Optional[str] = None) -> ToolExecResult:
        """Execute a command in the sandbox environment."""
        if not self.is_running:
            raise ToolError("Sandbox environment is not running")
            
        if self.sandbox_type == "docker":
            return await self._execute_docker_command(command, cwd)
        elif self.sandbox_type == "venv":
            return await self._execute_venv_command(command, cwd)
        else:
            raise ToolError(f"Unsupported sandbox type: {self.sandbox_type}")
    
    async def _start_docker_sandbox(self) -> None:
        """Start a Docker-based sandbox."""
        # Check if Docker is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode != 0:
                raise ToolError("Docker is not available")
        except FileNotFoundError:
            raise ToolError("Docker is not installed")
        
        # Create a temporary directory for the sandbox
        self.temp_dir = tempfile.mkdtemp(prefix="trae_sandbox_")
        
        # Copy workspace to sandbox directory
        sandbox_workspace = Path(self.temp_dir) / "workspace"
        shutil.copytree(self.workspace_path, sandbox_workspace, dirs_exist_ok=True)
        
        # Start Docker container
        docker_cmd = [
            "docker", "run", "-d", "-it",
            "--name", f"trae_sandbox_{os.getpid()}",
            "-v", f"{sandbox_workspace}:/workspace",
            "-w", "/workspace",
            "python:3.12-slim",
            "/bin/bash"
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise ToolError(f"Failed to start Docker container: {stderr.decode()}")
            
        self.container_id = stdout.decode().strip()
        
        # Install basic dependencies in the container
        await self._execute_docker_command("apt-get update && apt-get install -y git curl build-essential")
    
    async def _start_venv_sandbox(self) -> None:
        """Start a virtual environment-based sandbox."""
        # Create a temporary directory for the sandbox
        self.temp_dir = tempfile.mkdtemp(prefix="trae_sandbox_")
        
        # Copy workspace to sandbox directory
        sandbox_workspace = Path(self.temp_dir) / "workspace"
        shutil.copytree(self.workspace_path, sandbox_workspace, dirs_exist_ok=True)
        
        # Create virtual environment
        venv_path = Path(self.temp_dir) / "venv"
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "venv", str(venv_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        if proc.returncode != 0:
            raise ToolError("Failed to create virtual environment")
    
    async def _stop_docker_sandbox(self) -> None:
        """Stop the Docker-based sandbox."""
        if self.container_id:
            # Stop and remove container
            await asyncio.create_subprocess_exec(
                "docker", "stop", self.container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.create_subprocess_exec(
                "docker", "rm", self.container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            self.container_id = None
            
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None
    
    async def _stop_venv_sandbox(self) -> None:
        """Stop the virtual environment-based sandbox."""
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None
    
    async def _execute_docker_command(self, command: str, cwd: Optional[str] = None) -> ToolExecResult:
        """Execute a command in the Docker container."""
        if not self.container_id:
            raise ToolError("Docker container is not running")
            
        work_dir = cwd if cwd else "/workspace"
        docker_cmd = [
            "docker", "exec", "-w", work_dir, self.container_id,
            "/bin/bash", "-c", command
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        return ToolExecResult(
            output=stdout.decode(),
            error=stderr.decode() if stderr else None,
            error_code=proc.returncode or 0
        )
    
    async def _execute_venv_command(self, command: str, cwd: Optional[str] = None) -> ToolExecResult:
        """Execute a command in the virtual environment."""
        if not self.temp_dir:
            raise ToolError("Virtual environment is not set up")
            
        venv_path = Path(self.temp_dir) / "venv"
        activate_script = venv_path / "bin" / "activate"
        
        work_dir = cwd if cwd else str(Path(self.temp_dir) / "workspace")
        
        # Source the virtual environment and run the command
        full_command = f"source {activate_script} && cd {work_dir} && {command}"
        
        proc = await asyncio.create_subprocess_shell(
            full_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        return ToolExecResult(
            output=stdout.decode(),
            error=stderr.decode() if stderr else None,
            error_code=proc.returncode or 0
        )
    
    def get_workspace_path(self) -> str:
        """Get the sandbox workspace path."""
        if self.sandbox_type == "docker":
            return "/workspace"
        elif self.sandbox_type == "venv" and self.temp_dir:
            return str(Path(self.temp_dir) / "workspace")
        else:
            return str(self.workspace_path)


class SandboxTool(Tool):
    """Tool for managing sandboxed execution environments."""
    
    name = "sandbox"
    description = "Manage sandboxed execution environments for isolated dependency installation and execution"
    
    parameters = [
        ToolParameter(
            name="action",
            type="string",
            description="Action to perform: 'start', 'stop', 'status', or 'execute'",
            required=True
        ),
        ToolParameter(
            name="sandbox_type",
            type="string", 
            description="Type of sandbox: 'docker' or 'venv'",
            required=False
        ),
        ToolParameter(
            name="workspace_path",
            type="string",
            description="Path to the workspace to sandbox",
            required=False
        ),
        ToolParameter(
            name="command",
            type="string",
            description="Command to execute in the sandbox (for 'execute' action)",
            required=False
        ),
        ToolParameter(
            name="working_dir",
            type="string",
            description="Working directory for command execution",
            required=False
        )
    ]
    
    def __init__(self):
        super().__init__()
        self.sandboxes: Dict[str, SandboxEnvironment] = {}
        self.default_sandbox_id = "default"
    
    def get_name(self) -> str:
        return self.name
    
    def get_description(self) -> str:
        return self.description
    
    def get_parameters(self) -> list[ToolParameter]:
        return self.parameters
    
    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute the sandbox tool."""
        action = arguments.get("action")
        
        if action == "start":
            return await self._start_sandbox(arguments)
        elif action == "stop":
            return await self._stop_sandbox(arguments)
        elif action == "status":
            return await self._get_status()
        elif action == "execute":
            return await self._execute_command(arguments)
        else:
            return ToolExecResult(
                error=f"Unknown action: {action}",
                error_code=1
            )
    
    async def _start_sandbox(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Start a new sandbox environment."""
        workspace_path = arguments.get("workspace_path", os.getcwd())
        sandbox_type = arguments.get("sandbox_type", "docker")
        
        try:
            sandbox = SandboxEnvironment(workspace_path, sandbox_type)
            await sandbox.start()
            
            self.sandboxes[self.default_sandbox_id] = sandbox
            
            return ToolExecResult(
                output=f"Sandbox started successfully\n"
                      f"Type: {sandbox_type}\n"
                      f"Workspace: {workspace_path}\n"
                      f"Sandbox workspace: {sandbox.get_workspace_path()}"
            )
        except Exception as e:
            return ToolExecResult(
                error=f"Failed to start sandbox: {str(e)}",
                error_code=1
            )
    
    async def _stop_sandbox(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Stop the sandbox environment."""
        try:
            if self.default_sandbox_id in self.sandboxes:
                sandbox = self.sandboxes[self.default_sandbox_id]
                await sandbox.stop()
                del self.sandboxes[self.default_sandbox_id]
                
                return ToolExecResult(output="Sandbox stopped successfully")
            else:
                return ToolExecResult(
                    error="No active sandbox found",
                    error_code=1
                )
        except Exception as e:
            return ToolExecResult(
                error=f"Failed to stop sandbox: {str(e)}",
                error_code=1
            )
    
    async def _get_status(self) -> ToolExecResult:
        """Get the status of sandbox environments."""
        if self.default_sandbox_id in self.sandboxes:
            sandbox = self.sandboxes[self.default_sandbox_id]
            status = "running" if sandbox.is_running else "stopped"
            return ToolExecResult(
                output=f"Sandbox status: {status}\n"
                      f"Type: {sandbox.sandbox_type}\n"
                      f"Workspace: {sandbox.get_workspace_path()}"
            )
        else:
            return ToolExecResult(output="No sandbox environment found")
    
    async def _execute_command(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute a command in the sandbox."""
        command = arguments.get("command")
        working_dir = arguments.get("working_dir")
        
        if not command:
            return ToolExecResult(
                error="Command is required for execute action",
                error_code=1
            )
        
        if self.default_sandbox_id not in self.sandboxes:
            return ToolExecResult(
                error="No active sandbox found. Please start a sandbox first.",
                error_code=1
            )
        
        try:
            sandbox = self.sandboxes[self.default_sandbox_id]
            return await sandbox.execute_command(command, working_dir)
        except Exception as e:
            return ToolExecResult(
                error=f"Failed to execute command: {str(e)}",
                error_code=1
            )