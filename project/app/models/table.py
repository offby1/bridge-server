from django.contrib import admin
from django.db import models
from django.urls import reverse
from django.utils.html import format_html

from . import SEAT_CHOICES


class TableException(Exception):
    pass


class TableManager(models.Manager):
    def get_nonfull(self):
        return self.annotate(num_seats=models.Count("seat")).filter(num_seats__lt=4)


class Table(models.Model):
    objects = TableManager()

    def players_by_direction(self):
        seats = self.seat_set.all()
        return {s.direction: s.player for s in seats}

    def as_link(self):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("app:table-detail", kwargs=dict(pk=self.pk)),
            str(self).title(),
        )

    def as_tuples(self):
        return [(SEAT_CHOICES[d], p) for d, p in self.players_by_direction().items()]

    def __str__(self):
        playaz = ", ".join([f"{d}: {p}" for d, p in self.as_tuples()])
        return f"Table {self.id} ({playaz})"


admin.site.register(Table)
