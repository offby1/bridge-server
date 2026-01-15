"""
Pytest configuration for the Bridge project.
"""

import os

import pytest

# Allow Django database operations in async context for Playwright tests
# This is necessary because pytest-playwright creates an async event loop
# but Django's database operations are synchronous
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


# Note: Static files (CSS/JS) don't load properly in Django's test server
# even with WhiteNoise configured. This is a known Django testing limitation.
# Tests focus on HTML structure and functionality rather than visual appearance.


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
