# A "board" is a little tray with four slots, labeled "North", "East", "West", and "South".  The labels might be red, indicating that that pair is vulnerable; or not.
# https://en.wikipedia.org/wiki/Board_(bridge)
# One of the four slots says "dealer" next to it.
# In each slot are -- you guessed it -- 13 cards.  The board is thus a pre-dealt hand.
from django.db import models


class Board(models.Model):
    ns_vulnerable = models.BooleanField()
    ew_vulnerable = models.BooleanField()

    dealer = models.SmallIntegerField()  # corresponds to bridge library's "direction"

    cards = models.CharField(max_length=104)

    # Hmm, if we delete a table, and if the table is associated with a transcript ... what happens to the transcript?
    table = models.ForeignKey("Table", on_delete=models.CASCADE)
