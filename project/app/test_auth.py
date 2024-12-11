import base64

import pytest
from django.test import Client
from django.urls import reverse


def test_logging_in(db, usual_setup, settings) -> None:
    c = Client()

    assert c.login(username="Jeremy Northam", password=".") is True
    first_sk = "SECRETSECRETYAAAAA"
    settings.API_SKELETON_KEY = first_sk
    assert c.login(username="Jeremy Northam", password=first_sk) is True

    second_sk = "WHATCHOOLOOKINAT"
    settings.API_SKELETON_KEY = second_sk
    assert c.login(username="Jeremy Northam", password=first_sk) is False
    assert c.login(username="Jeremy Northam", password=second_sk) is True


@pytest.mark.parametrize(("password", "expected_status"), [(".", 200), ("wat", 403)])
def test_basic_auth(db, usual_setup, settings, password, expected_status) -> None:
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"Jeremy Northam:{password}".encode()).decode()
    }

    c = Client(headers=headers)
    response = c.get(
        reverse("app:serialized-hand-detail", args=[1]),
    )
    assert response.status_code == expected_status


def test_basic_auth_deals_with_improperly_encoded_stuff(db, usual_setup, settings) -> None:
    headers = {"Authorization": "Basic " + "Garbage! I am not base64-encoded."}

    c = Client(headers=headers)
    response = c.get(
        reverse("app:serialized-hand-detail", args=[1]),
    )
    assert response.status_code == 403

    pw = base64.b64encode(b"OK, so, like, I'm base64-encoded, but ain't got no colon").decode()
    headers = {"Authorization": "Basic " + pw}

    c = Client(headers=headers)
    response = c.get(
        reverse("app:serialized-hand-detail", args=[1]),
    )
    assert response.status_code == 403
