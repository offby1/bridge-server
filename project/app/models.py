from django.contrib import admin, auth
from django.db import models
from django.urls import reverse
from django.utils.html import format_html

# FWIW, https://docs.djangoproject.com/en/4.2/howto/custom-model-fields/#our-example-object demonstrates a Django model
# for a bridge hand.


class Table(models.Model):
    name = models.CharField(max_length=100, unique=True)

    # north = models.ForeignKey("Player")
    # east = models.ForeignKey("Player")
    # south = models.ForeignKey("Player")
    # west = models.ForeignKey("Player")

    # TODO -- a constraint that says all the players gotta be different

    def __str__(self):
        return f"{self.name}: {', '.join([str(p) for p in self.player_set.all()])}"


admin.site.register(Table)


class Player(models.Model):
    user = models.OneToOneField(
        auth.models.User,
        on_delete=models.CASCADE,
    )
    table = models.ForeignKey(
        "Table",
        blank=True,
        null=True,
        db_comment="If NULL, then I'm in the lobby",
        on_delete=models.CASCADE,
    )

    @property
    def name(self):
        return self.user.username

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:player", kwargs=dict(pk=self.pk)),
            self.name,
        )

    def __str__(self):
        return self.name


admin.site.register(Player)


class Hand(models.Model):
    table_played_at = models.ForeignKey("Table", on_delete=models.CASCADE)


admin.site.register(Hand)
