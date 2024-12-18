import base64

import pytest
from django.test import Client
from django.urls import reverse


def kablooey(*args, **kwargs) -> None:
    msg = "Oh no! Someone called some function they weren't s'posed to!!"
    raise Exception(msg)


@pytest.fixture
def no_pbkdf2(monkeypatch) -> None:
    import django.utils.crypto

    monkeypatch.setattr(django.utils.crypto, "pbkdf2", kablooey)


# check if there's *already* a valid session, and if so, just return an empty 200
def test_already_logged_in(usual_setup, no_pbkdf2) -> None:
    c = Client()
    assert c.login(username="Jeremy Northam", password=".") is True

    response = c.get(
        reverse("app:three-way-login"),
    )

    assert response.status_code == 200


def test_token_auth(usual_setup, no_pbkdf2, settings) -> None:
    c = Client()

    response = c.get(
        reverse("app:three-way-login"),
        headers={"Authorization": "Token Oh Whoops " + settings.API_SKELETON_KEY},  # type: ignore [arg-type]
    )

    assert response.status_code == 403
    assert "sessionid" not in response.cookies

    response = c.get(
        reverse("app:three-way-login"),
        headers={"Authorization": "Token " + settings.API_SKELETON_KEY},  # type: ignore [arg-type]
    )

    assert response.status_code == 200
    assert "sessionid" in response.cookies


def test_basic_auth(db, usual_setup, settings) -> None:
    c = Client()

    response = c.get(
        reverse("app:three-way-login"),
        headers={"Authorization": "Token Oh Whoops " + settings.API_SKELETON_KEY},  # type: ignore [arg-type]
    )

    assert response.status_code == 403
    assert "sessionid" not in response.cookies

    response = c.get(
        reverse("app:three-way-login"),
        headers={"Authorization": "Basic " + base64.b64encode(b"Jeremy Northam:.").decode()},  # type: ignore [arg-type]
    )

    assert response.status_code == 200
    assert "sessionid" in response.cookies


def test_basic_auth_deals_with_improperly_encoded_stuff(db, usual_setup, settings) -> None:
    headers = {"Authorization": "Basic " + "Garbage! I am not base64-encoded."}

    c = Client(headers=headers)
    response = c.get(
        reverse("app:three-way-login", args=[1]),
    )
    assert response.status_code == 403

    pw = base64.b64encode(b"OK, so, like, I'm base64-encoded, but ain't got no colon").decode()
    headers = {"Authorization": "Basic " + pw}

    c = Client(headers=headers)
    response = c.get(
        reverse("app:three-way-login", args=[1]),
    )
    assert response.status_code == 403
