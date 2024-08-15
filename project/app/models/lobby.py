from django.db import models


class LobbyMessage(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    player = models.ForeignKey("Player", on_delete=models.CASCADE)
    message = models.TextField(max_length=128)
