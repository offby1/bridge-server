import base64

import django.contrib.auth.hashers
import pytest
from django.test import Client
from django.urls import reverse

KABLOOEY_MESSAGE = "Oh no! Someone called some function they weren't s'posed to!!"


def kablooey(*args, **kwargs) -> None:
    raise Exception(KABLOOEY_MESSAGE)


@pytest.fixture
def no_pbkdf2(monkeypatch) -> None:
    monkeypatch.setattr(django.contrib.auth.hashers, "pbkdf2", kablooey)


# check if there's *already* a valid session, and if so, just return an empty 200
def test_already_logged_in(usual_setup, monkeypatch) -> None:
    c = Client()
    assert c.login(username="Jeremy Northam", password=".") is True

    with monkeypatch.context() as m:
        m.setattr(django.contrib.auth.hashers, "pbkdf2", kablooey)
        response = c.get(
            reverse("app:three-way-login"),
        )

    assert response.status_code == 200


def test_no_credentials_at_all() -> None:
    c = Client()

    response = c.get(
        reverse("app:three-way-login"),
    )

    assert response.status_code == 403


def test_wrong_password(usual_setup) -> None:
    c = Client(
        headers={"Authorization": "Basic " + base64.b64encode(b"Jeremy Northam:whoopsie").decode()},  # type: ignore [arg-type]
    )

    response = c.get(
        reverse("app:three-way-login"),
    )

    assert response.status_code == 403


def test_that_im_monkeypatching_the_right_thing(usual_setup, no_pbkdf2) -> None:
    # It's easy to get this wrong.
    c = Client()
    with pytest.raises(Exception) as e:
        c.get(
            reverse("app:three-way-login"),
            headers={
                "Authorization": "Basic " + base64.b64encode(b"Jeremy Northam:whoopsie").decode()
            },  # type: ignore [arg-type]
        )
    assert str(e.value) == KABLOOEY_MESSAGE


def test_username_and_password(usual_setup) -> None:
    total_bogosity = base64.b64encode(b"dingle:berry").decode()

    c = Client()

    response = c.get(
        reverse("app:three-way-login"),
        headers={"Authorization": total_bogosity},  # type: ignore [arg-type]
    )

    assert response.status_code == 403
    assert "sessionid" not in response.cookies

    c = Client()

    response = c.get(
        reverse("app:three-way-login"),
        headers={"Authorization": "Basic " + base64.b64encode(b"Jeremy Northam:.").decode()},  # type: ignore [arg-type]
    )

    assert response.status_code == 200
    assert "sessionid" in response.cookies


def test_user_primary_key_and_skeleton_key(usual_setup, settings) -> None:
    c = Client()

    response = c.get(
        reverse("app:three-way-login"),
        headers={
            "Authorization": "Basic "
            + base64.b64encode(f"1:{settings.API_SKELETON_KEY}".encode()).decode()
        },  # type: ignore [arg-type]
    )

    assert response.status_code == 200
    assert "sessionid" in response.cookies


def test_basic_auth_deals_with_improperly_encoded_stuff(usual_setup, settings) -> None:
    headers = {"Authorization": "Basic " + "Garbage! I am not base64-encoded."}

    c = Client(headers=headers)
    response = c.get(
        reverse("app:three-way-login"),
    )
    assert response.status_code == 403

    pw = base64.b64encode(b"OK, so, like, I'm base64-encoded, but ain't got no colon").decode()
    headers = {"Authorization": "Basic " + pw}

    c = Client(headers=headers)
    response = c.get(
        reverse("app:three-way-login"),
    )
    assert response.status_code == 403
