# Generated by Django 3.2 on 2021-05-19 00:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('utils', '0005_alter_directory_owner'),
    ]

    operations = [
        migrations.AlterField(
            model_name='file',
            name='content',
            field=models.FileField(blank=True, default='', null=True, upload_to='users_files/'),
        ),
    ]
