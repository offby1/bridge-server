"""
Playwright UI tests for Bridge server.

These tests use real browsers to test the user interface.
Run with: pytest -m playwright --headed
"""

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.playwright

# Get the User model
User = get_user_model()


@pytest.fixture
def authenticated_user(db):
    """Create a test user with player."""
    from app.models import Player

    user = User.objects.create_user(username="testplayer", password="testpass123")
    player = Player.objects.create(user=user)
    return user, player


@pytest.fixture
def completed_hand(db, authenticated_user):
    """Create a completed hand with all four hands visible."""
    from datetime import datetime, timedelta, timezone

    from app.models import Board, Hand, Player, Tournament

    user, player = authenticated_user

    # Create three more players for the other seats
    users_players = [authenticated_user]
    for seat in ["north", "east", "west"]:
        u = User.objects.create_user(username=seat, password="pass")
        p = Player.objects.create(user=u)
        users_players.append((u, p))

    # Create tournament and board
    tournament = Tournament.objects.create(
        play_completion_deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    # Mark tournament as completed after creation to avoid save() issues
    tournament.completed_at = datetime.now(timezone.utc)
    tournament.save()

    # Create simple board with dummy cards (13 cards each, 26 chars total)
    # Cards format: 2 chars per card (suit glyph + rank), 13 cards = 26 chars
    board = Board.objects.create(
        tournament=tournament,
        display_number=1,
        dealer="N",
        ns_vulnerable=False,
        ew_vulnerable=False,
        north_cards="♠A♠K♠Q♠J♠T♠9♠8♠7♠6♠5♠4♠3♠2",  # All spades for simplicity
        south_cards="♥A♥K♥Q♥J♥T♥9♥8♥7♥6♥5♥4♥3♥2",  # All hearts
        east_cards="♦A♦K♦Q♦J♦T♦9♦8♦7♦6♦5♦4♦3♦2",  # All diamonds
        west_cards="♣A♣K♣Q♣J♣T♣9♣8♣7♣6♣5♣4♣3♣2",  # All clubs
    )

    # Create hand with all four players (note: Hand uses capitalized field names)
    hand = Hand.objects.create(
        board=board,
        North=users_players[1][1],
        South=users_players[0][1],
        East=users_players[2][1],
        West=users_players[3][1],
        table_display_number=1,
        is_complete=True,
        open_access=True,  # Allow anyone to view all cards
    )

    return hand, users_players


@pytest.mark.skip(reason="CSS not served by Django test server - layout tests require static files")
@pytest.mark.django_db(transaction=True)
def test_four_hands_mobile_layout_stacks_vertically(page: Page, live_server, completed_hand):
    """
    Test that on mobile, the four-hands view stacks East/West vertically
    instead of side-by-side (eliminating horizontal scroll).
    """
    hand, users_players = completed_hand
    user, player = users_players[0]

    # Set mobile viewport (iPhone SE) BEFORE navigating so CSS media queries apply correctly
    page.set_viewport_size({"width": 375, "height": 667})

    # Login
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill('input[name="username"]', user.username)
    page.fill('input[name="password"]', "testpass123")
    page.click('input[type="submit"]')

    # Navigate to completed hand
    page.goto(f"{live_server.url}/hand/{hand.pk}/")

    # All four hands should be visible
    expect(page.locator("#north")).to_be_visible()
    expect(page.locator("#south")).to_be_visible()
    expect(page.locator("#east")).to_be_visible()
    expect(page.locator("#west")).to_be_visible()

    # Check that we don't have horizontal scroll
    # (The page width should not exceed viewport)
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    client_width = page.evaluate("document.documentElement.clientWidth")

    # Allow small differences due to scrollbars
    assert scroll_width - client_width < 20, (
        f"Horizontal scroll detected: {scroll_width} > {client_width}"
    )


@pytest.mark.skip(
    reason="CSS not served by Django test server - pseudo-elements require static files"
)
@pytest.mark.django_db(transaction=True)
def test_four_hands_mobile_shows_compass_labels(page: Page, live_server, completed_hand):
    """
    Test that prominent compass direction labels are visible on mobile,
    making it blindingly obvious which hand is which.
    """
    hand, users_players = completed_hand
    user, player = users_players[0]

    # Set mobile viewport BEFORE navigating so CSS media queries apply correctly
    page.set_viewport_size({"width": 375, "height": 667})

    # Login
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill('input[name="username"]', user.username)
    page.fill('input[name="password"]', "testpass123")
    page.click('input[type="submit"]')

    # Navigate to completed hand
    page.goto(f"{live_server.url}/hand/{hand.pk}/")

    # Check for compass labels with CSS pseudo-elements
    # We can't directly check ::before content, but we can verify the elements
    # exist and take screenshots to visually verify

    north_box = page.locator("#north").bounding_box()
    south_box = page.locator("#south").bounding_box()
    east_box = page.locator("#east").bounding_box()
    west_box = page.locator("#west").bounding_box()

    # All hands should have visible bounding boxes
    assert north_box is not None, "North hand not visible"
    assert south_box is not None, "South hand not visible"
    assert east_box is not None, "East hand not visible"
    assert west_box is not None, "West hand not visible"

    # Verify vertical stacking: top to bottom should be North, West, East, South
    assert north_box["y"] < west_box["y"], "North should be above West"
    assert west_box["y"] < east_box["y"], "West should be above East"
    assert east_box["y"] < south_box["y"], "East should be above South"

    # Take a screenshot for manual verification of compass labels
    page.screenshot(path="test_output_mobile_compass_labels.png")


@pytest.mark.skip(reason="CSS not served by Django test server - layout tests require static files")
@pytest.mark.django_db(transaction=True)
def test_four_hands_desktop_layout_unchanged(page: Page, live_server, completed_hand):
    """
    Test that on desktop, the four-hands view still uses the traditional
    bridge layout (East and West side-by-side).
    """
    hand, users_players = completed_hand
    user, player = users_players[0]

    # Login
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill('input[name="username"]', user.username)
    page.fill('input[name="password"]', "testpass123")
    page.click('input[type="submit"]')

    # Set desktop viewport BEFORE navigating so CSS media queries apply correctly
    page.set_viewport_size({"width": 1280, "height": 800})

    # Navigate to completed hand
    page.goto(f"{live_server.url}/hand/{hand.pk}/")

    # Get positions of hands
    east_box = page.locator("#east").bounding_box()
    west_box = page.locator("#west").bounding_box()

    # On desktop, East and West should be roughly at the same vertical position
    # (side by side, not stacked)
    assert east_box is not None, "East hand element not found"
    assert west_box is not None, "West hand element not found"
    assert abs(east_box["y"] - west_box["y"]) < 50, (
        "East and West should be side-by-side on desktop"
    )


@pytest.mark.django_db(transaction=True)
def test_login_page_loads(page: Page, live_server):
    """Simple smoke test: login page loads."""
    page.goto(f"{live_server.url}/accounts/login/")

    # Check that we're on the login page
    expect(page).to_have_title("Bridge")

    # Check login form exists
    expect(page.locator('input[name="username"]')).to_be_visible()
    expect(page.locator('input[name="password"]')).to_be_visible()

    # Take a screenshot for documentation
    page.screenshot(path="test_output_login_page.png")

    # Note: Static files (CSS/JS) don't load in Django test server by default.
    # This is a known limitation. The tests still validate HTML structure and functionality.
    # For visual regression testing with CSS, consider using production/staging environment.


@pytest.mark.skip(
    reason="CSS not served by Django test server - wrapping tests require static files"
)
@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_mobile_cards_fit_without_wrapping(page: Page, live_server, completed_hand):
    """
    Test that on mobile, all 13 cards in a suit fit on one row without wrapping.
    This preserves the Bridge convention of showing all cards in a suit together.
    """
    hand, users_players = completed_hand
    user, player = users_players[0]

    # Set mobile viewport BEFORE navigating so CSS media queries apply correctly
    page.set_viewport_size({"width": 375, "height": 667})

    # Login and navigate
    page.goto(f"{live_server.url}/accounts/login/")
    page.fill('input[name="username"]', user.username)
    page.fill('input[name="password"]', "testpass123")
    page.click('input[type="submit"]')
    page.goto(f"{live_server.url}/hand/{hand.pk}/")

    # Check each suit in North hand (visible because open_access=True)
    for suit in ["spades", "hearts", "diamonds", "clubs"]:
        suit_element = page.locator(f"#north .{suit}").first

        if suit_element.is_visible():
            # Get the suit container's bounding box
            suit_element.bounding_box()

            # Get all card divs within this suit
            cards = suit_element.locator("div").all()

            if len(cards) > 1:
                # Check that all cards are roughly at the same vertical position
                # (i.e., they're in a single row, not wrapped)
                first_card_box = cards[0].bounding_box()
                assert first_card_box is not None, f"First {suit} card not visible"
                first_card_y = first_card_box["y"]

                for card in cards[1:]:
                    card_box = card.bounding_box()
                    assert card_box is not None, f"{suit} card not visible"
                    card_y = card_box["y"]
                    # Allow small variance (5px) for alignment
                    assert abs(card_y - first_card_y) < 5, (
                        f"{suit} cards wrapped to multiple rows on mobile"
                    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--headed"])
