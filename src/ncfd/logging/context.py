"""
Logging context management for tracking execution flow.

Provides context variables for run_id, task_id, and other execution
context that should be automatically included in all log records.
"""

from __future__ import annotations

import contextvars
import uuid
from typing import Optional, Dict, Any
from datetime import datetime


# Context variables for automatic inclusion in logs
ctx_run_id = contextvars.ContextVar("run_id", default=None)
ctx_flow_id = contextvars.ContextVar("flow_id", default=None)
ctx_task_id = contextvars.ContextVar("task_id", default=None)
ctx_attempt = contextvars.ContextVar("attempt", default=0)
ctx_code_version = contextvars.ContextVar("code_version", default=None)
ctx_git_dirty = contextvars.ContextVar("git_dirty", default=None)
ctx_docker_image = contextvars.ContextVar("docker_image", default=None)
ctx_py_version = contextvars.ContextVar("py_version", default=None)
ctx_env = contextvars.ContextVar("env", default=None)
ctx_config_hash = contextvars.ContextVar("config_hash", default=None)


class LogContext:
    """
    Context manager for logging execution context.
    
    Automatically sets context variables for the duration of execution
    and provides methods to update them.
    """
    
    def __init__(
        self,
        run_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        task_id: Optional[str] = None,
        attempt: int = 0,
        code_version: Optional[str] = None,
        git_dirty: Optional[bool] = None,
        docker_image: Optional[str] = None,
        py_version: Optional[str] = None,
        env: Optional[str] = None,
        config_hash: Optional[str] = None,
    ):
        """
        Initialize logging context.
        
        Args:
            run_id: Unique run identifier (auto-generated if None)
            flow_id: Flow identifier
            task_id: Task identifier
            attempt: Retry attempt number (0-based)
            code_version: Git SHA
            git_dirty: Git dirty flag
            docker_image: Docker image tag
            py_version: Python version
            env: Environment (prod/stage/dev)
            config_hash: Configuration hash
        """
        self.run_id = run_id or f"r_{uuid.uuid4().hex[:10]}"
        self.flow_id = flow_id
        self.task_id = task_id
        self.attempt = attempt
        self.code_version = code_version
        self.git_dirty = git_dirty
        self.docker_image = docker_image
        self.py_version = py_version
        self.env = env
        self.config_hash = config_hash
        
        # Store original values for cleanup
        self._original_values = {}
    
    def __enter__(self):
        """Enter context and set all context variables."""
        # Store original values
        self._original_values = {
            'run_id': ctx_run_id.get(),
            'flow_id': ctx_flow_id.get(),
            'task_id': ctx_task_id.get(),
            'attempt': ctx_attempt.get(),
            'code_version': ctx_code_version.get(),
            'git_dirty': ctx_git_dirty.get(),
            'docker_image': ctx_docker_image.get(),
            'py_version': ctx_py_version.get(),
            'env': ctx_env.get(),
            'config_hash': ctx_config_hash.get(),
        }
        
        # Set new values
        ctx_run_id.set(self.run_id)
        if self.flow_id:
            ctx_flow_id.set(self.flow_id)
        if self.task_id:
            ctx_task_id.set(self.task_id)
        ctx_attempt.set(self.attempt)
        if self.code_version:
            ctx_code_version.set(self.code_version)
        if self.git_dirty is not None:
            ctx_git_dirty.set(self.git_dirty)
        if self.docker_image:
            ctx_docker_image.set(self.docker_image)
        if self.py_version:
            ctx_py_version.set(self.py_version)
        if self.env:
            ctx_env.set(self.env)
        if self.config_hash:
            ctx_config_hash.set(self.config_hash)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore original values."""
        # Restore original values
        for key, value in self._original_values.items():
            if value is not None:
                getattr(globals()[f"ctx_{key}"], 'set')(value)
            else:
                getattr(globals()[f"ctx_{key}"], 'set')(None)
    
    def update_task(self, task_id: str, attempt: int = 0):
        """Update task context within the same run."""
        ctx_task_id.set(task_id)
        ctx_attempt.set(attempt)
        self.task_id = task_id
        self.attempt = attempt
    
    def increment_attempt(self):
        """Increment retry attempt."""
        self.attempt += 1
        ctx_attempt.set(self.attempt)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for logging."""
        return {
            'run_id': self.run_id,
            'flow_id': self.flow_id,
            'task_id': self.task_id,
            'attempt': self.attempt,
            'code_version': self.code_version,
            'git_dirty': self.git_dirty,
            'docker_image': self.docker_image,
            'py_version': self.py_version,
            'env': self.env,
            'config_hash': self.config_hash,
        }


def set_context(
    run_id: Optional[str] = None,
    flow_id: Optional[str] = None,
    task_id: Optional[str] = None,
    attempt: int = 0,
    **kwargs
) -> LogContext:
    """
    Set logging context for the current execution.
    
    Args:
        run_id: Unique run identifier
        flow_id: Flow identifier
        task_id: Task identifier
        attempt: Retry attempt number
        **kwargs: Additional context parameters
        
    Returns:
        LogContext instance
    """
    return LogContext(
        run_id=run_id,
        flow_id=flow_id,
        task_id=task_id,
        attempt=attempt,
        **kwargs
    )


def get_current_context() -> Dict[str, Any]:
    """
    Get current logging context as dictionary.
    
    Returns:
        Dictionary with current context values
    """
    return {
        'run_id': ctx_run_id.get(),
        'flow_id': ctx_flow_id.get(),
        'task_id': ctx_task_id.get(),
        'attempt': ctx_attempt.get(),
        'code_version': ctx_code_version.get(),
        'git_dirty': ctx_git_dirty.get(),
        'docker_image': ctx_docker_image.get(),
        'py_version': ctx_py_version.get(),
        'env': ctx_env.get(),
        'config_hash': ctx_config_hash.get(),
    }


def generate_run_id() -> str:
    """Generate a new run ID."""
    return f"r_{uuid.uuid4().hex[:10]}"


def generate_task_id(prefix: str = "task") -> str:
    """Generate a new task ID."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def get_git_info() -> Dict[str, Any]:
    """
    Get git information for reproducibility.
    
    Returns:
        Dictionary with git SHA and dirty flag
    """
    try:
        import subprocess
        import sys
        
        # Get git SHA
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        git_sha = result.stdout.strip()[:12]  # Short SHA
        
        # Check if dirty
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
        )
        git_dirty = len(result.stdout.strip()) > 0
        
        return {
            'code_version': git_sha,
            'git_dirty': git_dirty
        }
    except Exception:
        return {
            'code_version': 'unknown',
            'git_dirty': None
        }


def get_system_info() -> Dict[str, Any]:
    """
    Get system information for reproducibility.
    
    Returns:
        Dictionary with system information
    """
    import sys
    import platform
    
    return {
        'py_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'platform': platform.platform(),
        'python_implementation': platform.python_implementation(),
    }
