import pytest
from django.contrib import auth
from django.test import Client
from django.urls import reverse

from .models import Player, Table


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content


@pytest.fixture()
def usual_setup(db):
    creation_kwargs = {}
    for username, attr in (
        ("Bob", "north"),
        ("Carol", "east"),
        ("Ted", "south"),
        ("Alice", "west"),
    ):
        u = auth.models.User.objects.create_user(username=username, password=username)
        p = Player.objects.create(user=u)
        creation_kwargs[attr] = p

    Table.objects.create(**creation_kwargs)


def test_player_names_are_links_to_detail_page(usual_setup):
    p = Player.objects.get(user__username="Bob")

    link = p.as_link()
    assert ">Bob," in link
    assert "href='/player/" in link


def test_only_bob_can_see_bobs_cards(usual_setup):
    c = Client()
    assert c.login(username="Bob", password="Bob"), "I guess I don't know how to make a test log in"
    response = c.get(reverse("app:player", kwargs=dict(pk=1)))

    assert response.context["show_cards_for"] == ["Bob"]
