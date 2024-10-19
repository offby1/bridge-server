import random

import tqdm
from app.models import Hand, Player, Table
from app.models.hand import AuctionError
from bridge.contract import Bid as libBid
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from faker import Faker

canned_calls = [
    "Pass",
    "1NT",
    "Double",
    "Pass",
    "2♣",
    "Pass",
    "Pass",
    "3NT",
    "Double",
    "Redouble",
    "Pass",
    "Pass",
    "Pass",
]


class Command(BaseCommand):
    def __init__(self):
        random.seed(0)  # TODO -- remove me when I'm done debugging

        # Use the same password for everybody, to speed things up :-)
        self.everybodys_password = make_password(".")
        super().__init__()

    def add_arguments(self, parser):
        parser.add_argument(
            "--players",
            default=14,
            type=int,
        )

    def generate_some_fake_calls_and_plays_at(self, table: Table, this_tables_index: int):
        calls_prefix = canned_calls[0:this_tables_index]

        # TODO -- just make a legal call; forget about canned_calls
        for c in calls_prefix:
            player = table.current_hand.auction.allowed_caller()
            call = libBid.deserialize(c)

            try:
                table.current_hand.add_call_from_player(player=player, call=call)
            except AuctionError as e:
                self.stdout.write(f"Hmm, {e}; will ignore it")
                continue
            else:
                table = Table.objects.get(pk=table.pk)

    def maybe_create_player(self, username: str) -> None:
        try:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"password": self.everybodys_password},
            )
            Player.objects.create(
                user=user,
                allow_bot_to_play_for_me=username != "bob",
            )

        except IntegrityError as e:
            self.stdout.write(f"Hmm, {e=}; will ignore it")

    def handle(self, *args, **options) -> None:
        fake = Faker()
        Faker.seed(0)

        with tqdm.tqdm(desc="players", total=options["players"], unit="p") as progress_bar:
            while Player.objects.count() < options["players"]:
                # Make sure we always have "bob", because his name is easy to type, and to remember :-)
                if not Player.objects.exists():
                    username = "bob"
                else:
                    username = fake.unique.first_name().lower()

                self.maybe_create_player(username)

                progress_bar.update()

        # Now partner 'em up
        while True:
            single_players = Player.objects.filter(partner__isnull=True).all()[0:2]

            if len(single_players) < 2:
                break

            single_players[0].partner_with(single_players[1])

        # Now seat those players.
        while True:
            unseated_player_one = Player.objects.filter(
                partner__isnull=False, seat__isnull=True
            ).first()

            if not unseated_player_one:
                break

            # find another unseated partnership
            unseated_player_two = (
                Player.objects.exclude(
                    pk__in={unseated_player_one.pk, unseated_player_one.partner.pk}
                )
                .filter(partner__isnull=False, seat__isnull=True)
                .first()
            )

            if not unseated_player_two:
                break

            Table.objects.create_with_two_partnerships(
                unseated_player_one,
                unseated_player_two,
            )

        # Don't ask me how but I've seen tables without hands
        last_table: Table | None = Table.objects.exclude(hand__isnull=True).order_by("-pk").first()
        assert last_table is not None
        self.generate_some_fake_calls_and_plays_at(last_table, Table.objects.count() - 1)

        # Now create a couple of unseated players.
        count_before = Player.objects.count()
        while Player.objects.count() < count_before + 3:
            self.maybe_create_player(fake.unique.first_name().lower())

        self.stdout.write(f"{Player.objects.count()} players at {Table.objects.count()} tables.")

        # Now find some tables with complete auctions, and play a few cards.
        playable_tables = [
            t
            for t in Table.objects.exclude(hand__isnull=True).all()
            if t.current_auction.found_contract
        ]
        t: Table
        for t in tqdm.tqdm(
            playable_tables,
            desc="tables",
            unit="t",
        ):
            h: Hand = t.current_hand
            for _ in range(2):
                assert h.player_who_may_play is not None
                assert h.player_who_may_play.most_recent_seat is not None
                some_hand = h.libraryThing(h.player_who_may_play.most_recent_seat)

                legal_cards = t.current_hand.get_xscript().legal_cards(some_hand=some_hand)
                if legal_cards:
                    chosen_card = random.choice(legal_cards)

                    self.stdout.write(f"At {t}, playing {chosen_card} from {legal_cards}")
                    t.current_hand.add_play_from_player(
                        player=h.player_who_may_play.libraryThing, card=chosen_card
                    )
                    t = Table.objects.get(pk=t.pk)

        for independent_player in Player.objects.filter(allow_bot_to_play_for_me=False).all():
            self.stdout.write(f"{independent_player} don't need no steenkin' bot!")
