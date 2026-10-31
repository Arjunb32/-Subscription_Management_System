"""Installed only by test_settings; no business models or migrations are added."""
from django.conf import settings
from django.db import models


class OwnedRecord(models.Model):
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=80)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
