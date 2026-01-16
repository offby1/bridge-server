"""Create a test board with a 9-card spade suit for testing mobile UI."""

from app.models import Board, Tournament
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a test board where North has a 9-card spade suit"

    def handle(self, *args, **options):
        # Create or get test tournament
        import datetime

        from django.utils import timezone

        tournament, created = Tournament.objects.get_or_create(
            display_number=9999,
            defaults={
                "tempo_seconds": 60,
                "signup_deadline": timezone.now() + datetime.timedelta(hours=24),
                "boards_per_round_per_table": 1,
            },
        )

        if created:
            self.stdout.write(f"Created test tournament #{tournament.display_number}")
        else:
            self.stdout.write(f"Using existing tournament #{tournament.display_number}")

        # Card format: suit unicode character + rank character (e.g., ♠A for Ace of Spades)
        # Suits: ♠ (spades), ♥ (hearts), ♦ (diamonds), ♣ (clubs)
        # Ranks: A,K,Q,J,T(10),9,8,7,6,5,4,3,2

        # North has: ♠ AKQJ98765 (9 spades!) + ♥ A + ♦ AK + ♣ A (13 cards = 26 chars)
        north_cards = "♠5♠6♠7♠8♠9♠J♠Q♠K♠A♥A♦K♦A♣A"

        # East: ♠ T4 + ♥ KT9 + ♦ QT9 + ♣ KQJT9 (13 cards = 26 chars)
        east_cards = "♠T♠4♥K♥T♥9♦Q♦T♦9♣K♣Q♣J♣T♣9"

        # South: ♠ 32 + ♥ QJ87 + ♦ J87 + ♣ 8765 (13 cards = 26 chars)
        south_cards = "♠3♠2♥Q♥J♥8♥7♦J♦8♦7♣8♣7♣6♣5"

        # West: ♥ 65432 + ♦ 65432 + ♣ 432 (13 cards = 26 chars)
        west_cards = "♥6♥5♥4♥3♥2♦6♦5♦4♦3♦2♣4♣3♣2"

        # Create or update the board
        board, created = Board.objects.update_or_create(
            tournament=tournament,
            display_number=1,
            defaults={
                "north_cards": north_cards,
                "east_cards": east_cards,
                "south_cards": south_cards,
                "west_cards": west_cards,
                "dealer": "N",
                "ns_vulnerable": False,
                "ew_vulnerable": False,
                "group": "A",
            },
        )

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} board #{board.display_number}"))
        self.stdout.write(f"Tournament: #{tournament.display_number} (pk={tournament.pk})")
        self.stdout.write(f"Board: #{board.display_number} (pk={board.pk})")
        self.stdout.write("")
        self.stdout.write("North has 9 spades: ♠ A K Q J 9 8 7 6 5")
        self.stdout.write(f"View board at: /app/board/{board.pk}/")
