from django.http import (
    HttpResponse,
)


def archive_view(request, *args, **kwargs):
    return HttpResponse(
        f"Imagine I am an archive of some completed table {request=} {args=} {kwargs=}"
    )
