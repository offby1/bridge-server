"""Which pages spend an SSE connection, and which don't.

Browsers allow six per origin, so this is a budget, and a page that takes a share of it
without using one should be noticed. Equally, a page that stops connecting by accident
goes quiet rather than breaking, which is the sort of bug you find weeks later.

So: assert the split, rather than trusting that nobody rearranged a template.
"""

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent / "templates"

EXTENDS_BASE = re.compile(r"{%\s*extends\s+[\"']base\.html[\"']\s*%}")
OPTS_OUT = re.compile(r"{%\s*block sse_connection\s*%}\s*{%\s*endblock")

# The pages that genuinely have something to listen for. Everything else extending
# base.html should opt out. Add to this list only if the page has an `sse-swap`
# element, or JavaScript that listens on window.bridgeEventSource.
PAGES_THAT_NEED_A_CONNECTION = {
    "interactive_hand.html",  # bidding box, own cards, table updates
    "read-only_hand.html",  # spectating a hand still being played
    "base_player_detail.html",  # chat
}


def _templates_extending_base() -> list[Path]:
    return sorted(p for p in TEMPLATES.glob("*.html") if EXTENDS_BASE.search(p.read_text()))


def test_we_found_some_templates_to_check() -> None:
    """Guard against the glob quietly matching nothing and this file passing vacuously."""
    assert len(_templates_extending_base()) > 10


@pytest.mark.parametrize("template", _templates_extending_base(), ids=lambda p: p.name)
def test_a_page_connects_only_if_it_has_something_to_listen_for(template: Path) -> None:
    opts_out = bool(OPTS_OUT.search(template.read_text()))
    should_connect = template.name in PAGES_THAT_NEED_A_CONNECTION

    if should_connect:
        assert not opts_out, (
            f"{template.name} needs the connection -- it has a subscriber -- but opts out"
        )
    else:
        assert opts_out, (
            f"{template.name} takes one of the browser's six connections and listens for "
            f"nothing. Add {{% block sse_connection %}}{{% endblock %}}, or add it to "
            f"PAGES_THAT_NEED_A_CONNECTION if it has grown a subscriber."
        )
