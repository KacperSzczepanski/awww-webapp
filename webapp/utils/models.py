from django.db import models
from datetime import datetime
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

class Entity(models.Model):
    timestamp = models.DateTimeField(default=timezone.now)
    validity_flag = models.BooleanField(default=True)

class Directory(Entity):
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True, default='')
    creation_date = models.DateTimeField(default=timezone.now)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    availability_flag = models.BooleanField(default=True)
    parent_dir = models.ForeignKey('Directory', on_delete=models.CASCADE, null=True)

    def validate(self):
        if self.name == '':
            raise ValidationError({'error': "Missing name"})
        if self.owner == None:
            raise ValidationError({'error': "Missing owner"})

class File(Entity):
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True, default='')
    creation_date = models.DateTimeField(default=timezone.now)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    availability_flag = models.BooleanField(default=True)
    parent_dir = models.ForeignKey('Directory', on_delete=models.CASCADE, null=True)

    content = models.FileField(upload_to='users_files/', default='')

    def validate(self):
        if self.name == '':
            raise ValidationError({'error': "Missing name"})
        if self.owner == None:
            raise ValidationError({'error': "Missing owner"})
        if self.content == '':
            raise ValidationError({'error': "Missing file"})