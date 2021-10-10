from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),

    path('add-dir/', views.add_dir, name="add_dir"),

    path('add-file/', views.add_file, name="add_file"),

    path('delete/', views.delete, name="delete"),
]