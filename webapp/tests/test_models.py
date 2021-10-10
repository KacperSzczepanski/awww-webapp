from django.test import TestCase
from django.db import IntegrityError
from django.utils.crypto import get_random_string
from django.core.exceptions import ValidationError
from django.core.files import File

import random
import mock

from utils.models import *

#tests for models

class DirectoryTests(TestCase):
    def test_missing_name(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        login = self.client.login(username='testuser', password='12345')

        with self.assertRaises(ValidationError):
            dir = Directory.objects.create(owner=self.user)
            dir.validate()

    def test_missing_owner(self):
        with self.assertRaises(IntegrityError):
            dir = Directory.objects.create(name="nazwa")
            dir.validate()

    def test_general(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        login = self.client.login(username='testuser', password='12345')

        parent_dir = Directory.objects.create(
            name = "nazwa1",
            owner = self.user
        )

        name = get_random_string(length=10)
        description = get_random_string(length=20)

        dir = Directory.objects.create(
            name = name,
            description = description,
            owner = self.user,
            parent_dir = parent_dir,
        )

        self.assertEqual(dir.name, name)
        self.assertEqual(dir.description, description)
        self.assertEqual(dir.owner, self.user)
        self.assertEqual(dir.parent_dir, parent_dir)

class FileTests(TestCase):
    def test_missing_name(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        login = self.client.login(username='testuser', password='12345')

        file_mock = mock.MagicMock(spec=File)
        file_mock.name = get_random_string(length=10)

        with self.assertRaises(ValidationError):
            dir = File(owner=self.user, content=file_mock)
            dir.validate()

    def test_missing_owner(self):
        with self.assertRaises(IntegrityError):
            dir = File.objects.create(name="nazwa")
            dir.validate()

    def test_missing_content(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        login = self.client.login(username='testuser', password='12345')

        with self.assertRaises(ValidationError):
            dir = File.objects.create(name="nazwa", owner=self.user)
            dir.validate()

    def test_general(self):
        self.user = User.objects.create_user(username='testuser', password='12345')
        login = self.client.login(username='testuser', password='12345')

        parent_dir = Directory.objects.create(
            name = "nazwa1",
            owner = self.user
        )

        name = get_random_string(length=10)
        description = get_random_string(length=20)
        file_mock = mock.MagicMock(spec=File)
        file_mock.name = get_random_string(length=10)

        file = File(name=name, description=description, owner=self.user, parent_dir=parent_dir, content=file_mock)

        self.assertEqual(file.name, name)
        self.assertEqual(file.description, description)
        self.assertEqual(file.owner, self.user)
        self.assertEqual(file.parent_dir, parent_dir)
        self.assertEqual(file.content, file_mock)