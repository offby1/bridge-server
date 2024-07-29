from django.contrib import admin
from django.db import models


# FWIW, https://docs.djangoproject.com/en/4.2/howto/custom-model-fields/#our-example-object demonstrates a Django model
# for a bridge hand.


class Club(models.Model):
    name = models.CharField(unique=True, max_length=100)

    def __str__(self):
        return self.name


admin.site.register(Club)


class Table(models.Model):
    name = models.CharField(max_length=100)
    club = models.ForeignKey("Club", on_delete=models.CASCADE)
    # north = models.ForeignKey("Player")
    # east = models.ForeignKey("Player")
    # south = models.ForeignKey("Player")
    # west = models.ForeignKey("Player")

    # TODO -- a constraint that says all the players gotta be different

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "name",
                    "club",
                ],
                name="composite_primary_key",
            ),
        ]


admin.site.register(Table)


class Player(models.Model):
    name = models.CharField(max_length=50, unique=True)
    table = models.ForeignKey(
        "Table",
        blank=True,
        null=True,
        db_comment="If NULL, then I'm in the lobby",
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return self.name


admin.site.register(Player)


class Hand(models.Model):
    table_played_at = models.ForeignKey("Table", on_delete=models.CASCADE)


admin.site.register(Hand)
