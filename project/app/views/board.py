from django.http import HttpResponse


def board_list_view(request, *args, **kwargs):
    return HttpResponse("Imagine a nice list of boards here")
