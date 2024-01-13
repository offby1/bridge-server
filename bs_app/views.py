from django.http import HttpResponse


def homepage(request):
    return HttpResponse(f"Welcome to the big ol' bridge club {request}")
