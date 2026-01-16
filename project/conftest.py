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


def pytest_sessionfinish(session, exitstatus):
    """
    Clean up test database and force exit to prevent hanging.

    pytest-django's live_server fixture keeps database connections open and
    creates non-daemon threads that don't terminate cleanly. This hook cleans
    up the database and forces exit if needed.
    """
    import threading
    import time

    # First, try to clean up the test database
    try:
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
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=5,
        )
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
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception:
        pass

    def force_exit():
        time.sleep(1)  # Give normal cleanup a chance
        # Force exit - live_server threads don't clean up properly
        # Use os._exit() instead of sys.exit() to bypass cleanup and terminate immediately
        os._exit(exitstatus)

    # Start the force-exit timer in a daemon thread
    timer = threading.Thread(target=force_exit, daemon=True)
    timer.start()


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
