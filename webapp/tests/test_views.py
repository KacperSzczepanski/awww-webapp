from django.test.client import Client
from django.test import TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string
from django.core.files.uploadedfile import SimpleUploadedFile
import random
import mock

from utils.models import *

class TestCaseRandomApp(TestCase):
    url = reverse("index")
    client: Client = None

    example_user: str = None
    example_user_password: str = None
    example_user_2: str = None
    example_user_2_password: str = None

    def login(self):
        self.assertTrue(self.client.login(
            username=self.example_user,
            password=self.example_user_password
        ))

    def login2(self):
        self.assertTrue(self.client.login(
            username=self.example_user_2,
            password=self.example_user_2_password
        ))

    def logout(self):
        self.client.logout()

    def setUp(self):
        self.example_user = 'User'
        self.example_user_password = 'haslo123testowe'

        user = User.objects.create(
            username=self.example_user
        )
        user.set_password(self.example_user_password)
        user.save()

        self.example_user_2 = self.example_user + '2'
        self.example_user_2_password = self.example_user_password + '2'

        user2 = User.objects.create(
            username=self.example_user_2
        )
        user2.set_password(self.example_user_2_password)
        user2.save()

        self.client = Client()

class IndexTests(TestCaseRandomApp):
    def test_accessible(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_logout_navbar(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'Login')
        self.assertContains(response, 'Register')
        self.assertNotContains(response, 'Add file')
        self.assertNotContains(response, 'Add directory')
        self.assertNotContains(response, 'Delete')
        self.assertNotContains(response, 'Logout')
        self.assertNotContains(response, 'Hi')

    def test_login_navbar(self):
        self.login()
        response = self.client.get(self.url)

        self.assertNotContains(response, 'Login')
        self.assertNotContains(response, 'Register')
        self.assertContains(response, 'Add file')
        self.assertContains(response, 'Add directory')
        self.assertContains(response, 'Delete')
        self.assertContains(response, 'Logout')
        self.assertContains(response, 'Hi')

class FilesViewsTests(TestCaseRandomApp):
    def test_files_view(self):
        name = 'nazwa_pliku'

        File.objects.create(
            name=name,
            owner=User.objects.get(username=self.example_user),
            content='/utils/tests/test_models.py'
        )

        self.login()
        response = self.client.get(self.url)
        self.assertContains(response, name)

    def test_files_views_2(self):
        name = 'nazwa_pliku'

        file = File(
            name=name,
            owner=User.objects.get(username=self.example_user),
            content='/utils/tests/test_models.py'
        )

        self.login()
        response = self.client.get(self.url)
        self.assertNotContains(response, name)

    def test_add_file(self):
        file_content = SimpleUploadedFile(
            "test.txt",
            str.encode('losowy content więc walnę w klawiaturę hytjngufbm ')
        )
        name = 'nazwa_pliku'
        desc = 'brak opisu bo zabraklo dlugopisu'

        self.login()

        response = self.client.post(reverse("add_file"), data={
            "file_name" : name,
            "file_desc" : desc,
            "dest_for_file": '-1',
            "file_file": file_content
        }, follow = True)

        self.assertContains(response, name)

    def test_add_file_with_get(self):
        file_content = SimpleUploadedFile(
            "test.txt",
            str.encode('losowy content więc walnę w klawiaturę hytjngufbm ')
        )
        name = 'nazwa_pliku'
        desc = 'brak opisu bo zabraklo dlugopisu'

        self.login()

        response = self.client.get(reverse("add_file"), data={
            "file_name" : name,
            "file_desc" : desc,
            "dest_for_file": '-1',
            "file_file": file_content
        }, follow = True)

        self.assertNotContains(response, name)

    def test_add_file_with_no_parent(self):
        file_content = SimpleUploadedFile(
            "test2.txt",
            str.encode('lubię fraktale')
        )
        name = 'plik27'
        desc = 'desc13'

        self.login()

        response = self.client.post(reverse("add_file"), data={
            "file_name" : name,
            "file_desc" : desc,
            "dest_for_file": 2137,
            "file_file": file_content
        }, follow = True)

        self.assertNotContains(response, name)

class DirectoryViewTests(TestCaseRandomApp):
    def test_dir_views(self):
        name = 'katalog'

        Directory.objects.create(
            name=name,
            owner=User.objects.get(username=self.example_user)
        )

        self.login()
        response = self.client.get(self.url)
        self.assertContains(response, name)

    def test_dir_views_2(self):
        name = 'katalog'

        dir = Directory(
            name=name,
            owner=User.objects.get(username=self.example_user)
        )

        self.login()
        response = self.client.get(self.url)
        self.assertNotContains(response, name)

    def test_add_dir(self):
        name = 'katalog'
        desc = 'a tu jest opis'

        self.login()

        response = self.client.post(reverse("add_dir"), data={
            "dir_name": name,
            "dir_desc": desc,
            "dest_for_dir": '-1'
        }, follow = True)

        self.assertContains(response, name)

    def test_add_dir_with_get(self):
        name = 'katalog'
        desc = 'a tu jest opis'

        self.login()

        response = self.client.get(reverse("add_dir"), data={
            "dir_name": name,
            "dir_desc": desc,
            "dest_for_dir": '-1'
        }, follow = True)

        self.assertNotContains(response, name)

    def test_add_dir_with_no_parent(self):
        name = 'katalog'
        desc = 'nigdy go nie dodano'

        self.login()

        response = self.client.post(reverse("add_dir"), data={
            'dir_name': name,
            'dir_desc': desc,
            'dest_for_dir': 1234567890
        }, follow = True)

        self.assertNotContains(response, name)


class TreeTests(TestCaseRandomApp):
    dir_names = ["" for i in range(10)]
    file_names = ["" for i in range(10)]

    def create_file(self, parent_dir, owner, layer):
        self.file_names[layer] = ('plik' + str(layer))

        file = File.objects.create(
            name = self.file_names[layer],
            owner = owner,
            parent_dir = parent_dir,
            description = 'otusz nie tym razem',
            content = SimpleUploadedFile(
                "test.txt",
                str.encode('ikjlhedwsxfaoijdsqefwjhbik dfsvceqjoi9huklpb dqsewfvc')
            )
        )

    def create_directory(self, parent_dir, owner, layer, max_layer):
        self.dir_names[layer] = ('folder' + str(layer))

        dir = Directory.objects.create(
            name = self.dir_names[layer],
            owner = owner,
            parent_dir = parent_dir,
            description = 'get_random_string(20)'
        )

        self.create_file(dir, owner, layer)

        if layer + 1 < max_layer:
            self.create_directory(dir, owner, (layer + 1), max_layer)

    def test_tree(self):
        self.login()
        self.create_directory(None, User.objects.get(username=self.example_user), 0, 10)
        response = self.client.get(self.url)

        for i in range(10):
            self.assertContains(response, self.dir_names[i])
            self.assertContains(response, self.file_names[i])

class DeleteViewTest(TestCaseRandomApp):
    def test_delete_dir(self):
        name = 'nazwa'
        desc = 'dri'

        dir = Directory.objects.create(
            name = name,
            description = desc,
            owner = User.objects.get(username=self.example_user)
        )

        self.login()

        response = self.client.get(self.url)

        self.assertContains(response, name)

        response = self.client.post(reverse("delete"), data={
            "to_delete": 1
        }, follow=True)

        self.assertNotContains(response, name)

    def test_delete_dir_with_get(self):
        name = 'nazwa'
        desc = 'dri'

        dir = Directory.objects.create(
            name = name,
            description = desc,
            owner = User.objects.get(username=self.example_user)
        )

        self.login()

        response = self.client.get(self.url)

        self.assertContains(response, name)

        response = self.client.get(reverse("delete"), data={
            "to_delete": 1
        }, follow=True)

        self.assertContains(response, name)

    def test_delete_file(self):
        file_content = SimpleUploadedFile(
            "test.txt",
            str.encode('hbjkoliusdkbjhgiodfshbkji')
        )
        name = 'plik'
        desc = 'csed'

        file = File.objects.create(
            name = name,
            description = desc,
            owner = User.objects.get(username=self.example_user),
            content = file_content
        )

        self.login()
        response = self.client.get(self.url)

        self.assertContains(response, name)

        response = self.client.post(reverse("delete"), data={
            "to_delete": 1
        }, follow=True)

        self.assertNotContains(response, name)

    def test_delete_file_with_get(self):
        file_content = SimpleUploadedFile(
            "test.txt",
            str.encode('hbjkoliusdkbjhgiodfshbkji')
        )
        name = 'plik'
        desc = 'csed'

        file = File.objects.create(
            name = name,
            description = desc,
            owner = User.objects.get(username=self.example_user),
            content = file_content
        )

        self.login()
        response = self.client.get(self.url)

        self.assertContains(response, name)

        response = self.client.get(reverse("delete"), data={
            "to_delete": 1
        }, follow=True)

        self.assertContains(response, name)

class NoAccessToOtherUsersFilesTest(TestCaseRandomApp):
    def test_no_access(self):
        name = 'nazwa'
        name2 = 'nawza2'

        dir1 = Directory.objects.create(
            name = name,
            owner = User.objects.get(username=self.example_user)
        )

        dir2 = Directory.objects.create(
            name = name2,
            owner = User.objects.get(username=self.example_user_2)
        )

        self.login2()
        response = self.client.get(self.url)

        self.assertContains(response, name2)
        self.assertNotContains(response, name)

        self.logout()
        self.login()
        response = self.client.get(self.url)

        self.assertContains(response, name)
        self.assertNotContains(response, name2)