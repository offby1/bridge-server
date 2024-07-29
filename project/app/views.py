from django.shortcuts import render

# Create your views here.


def duh(request):
    return render(request, "welcome.html")
