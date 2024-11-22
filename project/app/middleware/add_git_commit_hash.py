from django.conf import settings


class AddVersionHeaderMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response
        self.VERSION = settings.VERSION

    def __call__(self, request):
        response = self.get_response(request)
        response.headers["X-Bridge-Version"] = self.VERSION

        return response
