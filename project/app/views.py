from django.http import HttpResponse
from django.shortcuts import render

# Create your views here.


def duh(request):
    return HttpResponse("<html>My Samoyed is <em>really</em> hairy.</html>")
