import base64

from django.test import Client
from django.urls import reverse


def test_various_auth_flavors(db, usual_setup):
    c = Client()

    response = c.post(
        reverse("app:basic-auth-login"), data={"username": "Jeremy Northam", "password": "."}
    )
    assert response.status_code == 200

    c = Client()

    response = c.post(
        reverse("app:basic-auth-login"),
        data={"username": "Jeremy Northam", "password": "oh crap, forgot my password"},
    )
    assert response.status_code == 403

    response = c.post(
        reverse("app:basic-auth-login"),
        headers={"Authorization": "Basic " + base64.b64encode(b"Jeremy Northam:.").decode()},
    )
    assert response.status_code == 200

    c = Client()

    response = c.post(
        reverse("app:basic-auth-login"),
        headers={
            "Authorization": "Basic "
            + base64.b64encode(b"Jeremy Northam:Crap, forgot my password again").decode()
        },
    )
    assert response.status_code == 403


def test_already_logged_in(db, usual_setup):
    c = Client()
    c.login(username="Jeremy Northam", password=".")

    response = c.post(
        reverse("app:basic-auth-login"),
    )
    assert response.status_code == 200
