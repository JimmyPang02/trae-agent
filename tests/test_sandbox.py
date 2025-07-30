# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for sandbox functionality."""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trae_agent.tools.sandbox_bash_tool import SandboxAwareBashTool, SandboxBashTool
from trae_agent.tools.sandbox_tool import SandboxEnvironment, SandboxTool


class TestSandboxEnvironment(unittest.TestCase):
    """Test cases for SandboxEnvironment."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace_path = Path(self.temp_dir) / "test_workspace"
        self.workspace_path.mkdir(exist_ok=True)
        
        # Create a test file
        (self.workspace_path / "test.txt").write_text("test content")

    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('shutil.which')
    def test_venv_sandbox_init(self, mock_which):
        """Test virtual environment sandbox initialization."""
        mock_which.return_value = "/usr/bin/python"
        
        sandbox = SandboxEnvironment(str(self.workspace_path), "venv")
        self.assertEqual(sandbox.sandbox_type, "venv")
        self.assertEqual(sandbox.workspace_path, self.workspace_path)
        self.assertFalse(sandbox.is_running)

    def test_docker_sandbox_init(self):
        """Test Docker sandbox initialization."""
        sandbox = SandboxEnvironment(str(self.workspace_path), "docker")
        self.assertEqual(sandbox.sandbox_type, "docker")
        self.assertEqual(sandbox.workspace_path, self.workspace_path)
        self.assertFalse(sandbox.is_running)

    def test_unsupported_sandbox_type(self):
        """Test unsupported sandbox type."""
        sandbox = SandboxEnvironment(str(self.workspace_path), "unsupported")
        
        with pytest.raises(Exception):
            asyncio.run(sandbox.start())


class TestSandboxTool(unittest.TestCase):
    """Test cases for SandboxTool."""

    def setUp(self):
        """Set up test environment."""
        self.sandbox_tool = SandboxTool()

    @pytest.mark.asyncio
    async def test_start_sandbox_action(self):
        """Test start sandbox action."""
        with patch.object(SandboxEnvironment, 'start', new_callable=AsyncMock) as mock_start:
            mock_start.return_value = None
            
            result = await self.sandbox_tool.execute({
                "action": "start",
                "workspace_path": "/tmp/test",
                "sandbox_type": "venv"
            })
            
            self.assertIsNone(result.error)
            self.assertIn("Sandbox started successfully", result.output)

    @pytest.mark.asyncio
    async def test_stop_sandbox_action(self):
        """Test stop sandbox action."""
        # First start a sandbox
        with patch.object(SandboxEnvironment, 'start', new_callable=AsyncMock):
            await self.sandbox_tool.execute({
                "action": "start",
                "workspace_path": "/tmp/test",
                "sandbox_type": "venv"
            })
        
        # Then stop it
        with patch.object(SandboxEnvironment, 'stop', new_callable=AsyncMock) as mock_stop:
            mock_stop.return_value = None
            
            result = await self.sandbox_tool.execute({"action": "stop"})
            
            self.assertIsNone(result.error)
            self.assertIn("Sandbox stopped successfully", result.output)

    @pytest.mark.asyncio
    async def test_status_action(self):
        """Test status action."""
        result = await self.sandbox_tool.execute({"action": "status"})
        
        self.assertIsNone(result.error)
        self.assertIn("No sandbox environment found", result.output)

    @pytest.mark.asyncio
    async def test_execute_action_without_sandbox(self):
        """Test execute action without active sandbox."""
        result = await self.sandbox_tool.execute({
            "action": "execute",
            "command": "echo hello"
        })
        
        self.assertIsNotNone(result.error)
        self.assertIn("No active sandbox found", result.error)

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        """Test unknown action."""
        result = await self.sandbox_tool.execute({"action": "unknown"})
        
        self.assertIsNotNone(result.error)
        self.assertIn("Unknown action", result.error)


class TestSandboxAwareBashTool(unittest.TestCase):
    """Test cases for SandboxAwareBashTool."""

    def setUp(self):
        """Set up test environment."""
        self.bash_tool = SandboxAwareBashTool()

    def test_should_auto_sandbox_pip_install(self):
        """Test auto sandbox detection for pip install."""
        self.assertTrue(self.bash_tool._should_auto_sandbox("pip install numpy"))
        self.assertTrue(self.bash_tool._should_auto_sandbox("pip3 install requests"))

    def test_should_auto_sandbox_npm_install(self):
        """Test auto sandbox detection for npm install."""
        self.assertTrue(self.bash_tool._should_auto_sandbox("npm install express"))
        self.assertTrue(self.bash_tool._should_auto_sandbox("npm i lodash"))

    def test_should_auto_sandbox_other_commands(self):
        """Test auto sandbox detection for other package managers."""
        self.assertTrue(self.bash_tool._should_auto_sandbox("yarn add react"))
        self.assertTrue(self.bash_tool._should_auto_sandbox("poetry install"))
        self.assertTrue(self.bash_tool._should_auto_sandbox("conda install pandas"))

    def test_should_not_auto_sandbox_regular_commands(self):
        """Test that regular commands don't trigger sandbox."""
        self.assertFalse(self.bash_tool._should_auto_sandbox("ls -la"))
        self.assertFalse(self.bash_tool._should_auto_sandbox("cd /tmp"))
        self.assertFalse(self.bash_tool._should_auto_sandbox("python script.py"))

    @pytest.mark.asyncio
    async def test_execute_without_sandbox(self):
        """Test execution without sandbox for non-package commands."""
        with patch('trae_agent.tools.bash_tool.BashTool.execute', new_callable=AsyncMock) as mock_execute:
            from trae_agent.tools.base import ToolExecResult
            mock_execute.return_value = ToolExecResult(output="hello")
            
            result = await self.bash_tool.execute({"command": "echo hello"})
            
            mock_execute.assert_called_once()
            self.assertEqual(result.output, "hello")

    @pytest.mark.asyncio
    async def test_execute_with_auto_sandbox(self):
        """Test execution with auto sandbox for package install commands."""
        with patch.object(self.bash_tool.sandbox_tool, '_get_status', new_callable=AsyncMock) as mock_status, \
             patch.object(self.bash_tool.sandbox_tool, '_start_sandbox', new_callable=AsyncMock) as mock_start, \
             patch.object(self.bash_tool.sandbox_tool, '_execute_command', new_callable=AsyncMock) as mock_execute:
            
            from trae_agent.tools.base import ToolExecResult
            
            # Mock sandbox not found initially
            mock_status.return_value = ToolExecResult(output="No sandbox environment found")
            mock_start.return_value = ToolExecResult(output="Sandbox started")
            mock_execute.return_value = ToolExecResult(output="Package installed")
            
            result = await self.bash_tool.execute({"command": "pip install numpy"})
            
            mock_start.assert_called_once()
            mock_execute.assert_called_once()
            self.assertIn("[SANDBOX]", result.output)


class TestSandboxBashTool(unittest.TestCase):
    """Test cases for SandboxBashTool."""

    def setUp(self):
        """Set up test environment."""
        self.sandbox_tool = MagicMock()
        self.bash_tool = SandboxBashTool(self.sandbox_tool)

    @pytest.mark.asyncio
    async def test_execute_with_sandbox_running(self):
        """Test execution when sandbox is running."""
        from trae_agent.tools.base import ToolExecResult
        
        self.sandbox_tool._get_status = AsyncMock(return_value=ToolExecResult(output="running"))
        self.sandbox_tool._execute_command = AsyncMock(return_value=ToolExecResult(output="command output"))
        
        result = await self.bash_tool.execute({"command": "ls -la"})
        
        self.sandbox_tool._execute_command.assert_called_once()
        self.assertEqual(result.output, "command output")

    @pytest.mark.asyncio
    async def test_execute_fallback_to_regular_bash(self):
        """Test fallback to regular bash when sandbox fails."""
        from trae_agent.tools.base import ToolExecResult
        
        self.sandbox_tool._get_status = AsyncMock(side_effect=Exception("Sandbox error"))
        
        with patch('trae_agent.tools.bash_tool.BashTool.execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = ToolExecResult(output="regular bash output")
            
            result = await self.bash_tool.execute({"command": "ls -la"})
            
            mock_execute.assert_called_once()
            self.assertEqual(result.output, "regular bash output")

    @pytest.mark.asyncio
    async def test_execute_without_sandbox_tool(self):
        """Test execution when no sandbox tool is provided."""
        bash_tool = SandboxBashTool(None)
        
        with patch('trae_agent.tools.bash_tool.BashTool.execute', new_callable=AsyncMock) as mock_execute:
            from trae_agent.tools.base import ToolExecResult
            mock_execute.return_value = ToolExecResult(output="regular bash output")
            
            result = await bash_tool.execute({"command": "ls -la"})
            
            mock_execute.assert_called_once()
            self.assertEqual(result.output, "regular bash output")


if __name__ == '__main__':
    unittest.main()