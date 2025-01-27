from django.conf import settings


class AddVersionHeaderMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response
        self.VERSION = settings.VERSION
        self.GIT_SYMBOLIC_REF = settings.GIT_SYMBOLIC_REF

    def __call__(self, request):
        response = self.get_response(request)
        response.headers["X-Bridge-Version"] = self.VERSION
        response.headers["X-Bridge-Git-Symbolic-Ref"] = self.GIT_SYMBOLIC_REF

        return response
