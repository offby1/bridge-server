from django.db import connection


class AddRequestIdToSQLConnectionMiddleware:
    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SET application_name = %s", [request.id])
        return self.get_response(request)
