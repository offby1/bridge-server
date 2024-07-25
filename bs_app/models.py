from django.db import models


# FWIW, https://docs.djangoproject.com/en/4.2/howto/custom-model-fields/#our-example-object demonstrates a Django model
# for a bridge hand.


class Club(models.Model):
    name = models.Charfield(max_length=100)


class Table(models.Model):
    name = models.Charfield(max_length=100)
    club = models.ForeignKey("Club")
    north = models.ForeignKey("Player")
    east = models.ForeignKey("Player")
    south = models.ForeignKey("Player")
    west = models.ForeignKey("Player")

    # TODO -- a constraint that says all the players gotta be different


class Player(models.Model):
    table = models.ForeignKey(
        "Table",
        null=True,
        db_comment="If NULL, then I'm in the lobby",
    )


class Hand(models.Model):
    table_played_at = models.ForeignKey("Table")
