from django.test import Client


def test_we_gots_a_home_page():
    c = Client()
    response = c.get("/")
    assert b"Welcome" in response.content
