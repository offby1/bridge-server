from django.test import Client, TestCase


class SmokeTest(TestCase):
    def test_we_gots_a_home_page(self):
        c = Client()
        response = c.get("/")
        self.assertContains(response, "Welcome")
