from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

MAX_INT_LEN = 10
MAX_STR_LEN = 100

class Dataset(models.Model):
    index = models.CharField(max_length=MAX_STR_LEN)
    mapping = models.CharField(max_length=MAX_STR_LEN)
    author = models.ForeignKey(User)
    daterange = models.TextField()

class ScriptProject(models.Model):
    name = models.CharField(max_length=MAX_STR_LEN)
    desc = models.TextField()
    entrance_point = models.CharField(max_length=MAX_STR_LEN)
    arguments = models.TextField()
    last_modified = models.DateTimeField()

    def save(self, *args, **kwargs):
        """From http://stackoverflow.com/questions/1737017/django-auto-now-and-auto-now-add - update last_modified on save """
        self.last_modified = timezone.now()
        return super(ScriptProject, self).save(*args, **kwargs)
