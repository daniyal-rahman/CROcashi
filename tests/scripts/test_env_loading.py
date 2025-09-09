"""
Test environment loading functionality.
"""

import os
import pytest
from tests.utils.env_loader import setup_test_environment, get_test_env


def test_environment_loading():
    """Test that environment variables are properly loaded."""
    # Get current environment
    env = get_test_env()
    
    # Check that required variables are set
    assert 'PSQL_DSN' in env
    assert 'OPENAI_API_KEY' in env
    assert 'STORAGE_TYPE' in env
    assert 'LOCAL_STORAGE_ROOT' in env
    
    # Check that they have reasonable values
    assert env['PSQL_DSN'] is not None and len(env['PSQL_DSN']) > 0
    assert env['OPENAI_API_KEY'] is not None
    assert env['STORAGE_TYPE'] == 'local'
    assert env['LOCAL_STORAGE_ROOT'] is not None and len(env['LOCAL_STORAGE_ROOT']) > 0


def test_environment_fixture(test_env):
    """Test that the test_env fixture works."""
    assert isinstance(test_env, dict)
    assert 'PSQL_DSN' in test_env
    assert 'OPENAI_API_KEY' in test_env
    assert 'STORAGE_TYPE' in test_env
    assert 'LOCAL_STORAGE_ROOT' in test_env


def test_environment_variables_in_os():
    """Test that environment variables are actually set in os.environ."""
    # These should be set by the conftest.py
    assert 'PSQL_DSN' in os.environ
    assert 'OPENAI_API_KEY' in os.environ
    assert 'STORAGE_TYPE' in os.environ
    assert 'LOCAL_STORAGE_ROOT' in os.environ
    
    # Check values
    assert os.environ['PSQL_DSN'] is not None and len(os.environ['PSQL_DSN']) > 0
    assert os.environ['STORAGE_TYPE'] == 'local'


def test_setup_test_environment():
    """Test the setup_test_environment function directly."""
    # This should not raise any exceptions
    result = setup_test_environment()
    
    assert isinstance(result, dict)
    # Check that we have some environment variables
    assert len(result) > 0
    assert 'OPENAI_API_KEY' in result
    # PSQL_DSN might not be in result if it's already set in the environment
    assert 'STORAGE_TYPE' in result
