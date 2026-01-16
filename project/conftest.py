"""
Pytest configuration for the Bridge project.
"""

import os
import subprocess

import pytest

# Use test-specific settings that enable static file serving
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.test_settings")

# Allow Django database operations in async context for Playwright tests
# This is necessary because pytest-playwright creates an async event loop
# but Django's database operations are synchronous
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """
    Terminate test database connections and drop the database manually if pytest-django failed.

    The live_server fixture keeps database connections open, causing pytest-django's
    database teardown to fail. This hook cleans up after that failure, ensuring
    subsequent test runs can create the database fresh.
    """
    try:
        # Terminate all connections to the test database
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "postgres",
                "-c",
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = 'test_bridge' AND pid <> pg_backend_pid();",
            ],
            capture_output=True,
            check=False,
        )
        # Drop the test database if it still exists
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "postgres",
                "-c",
                "DROP DATABASE IF EXISTS test_bridge;",
            ],
            capture_output=True,
            check=False,
        )
    except Exception:
        # If docker isn't available, skip cleanup
        pass


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """
    Configure browser context for all Playwright tests.
    """
    return {
        **browser_context_args,
        # Increase viewport size for desktop tests
        "viewport": {"width": 1280, "height": 800},
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """
    Configure browser launch arguments.
    """
    return {
        **browser_type_launch_args,
        # Slow down actions slightly to make tests easier to follow in headed mode
        "slow_mo": 100,
    }
