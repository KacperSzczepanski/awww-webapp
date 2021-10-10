from django.shortcuts import render
from django.http import HttpResponse
from .models import *
from django.shortcuts import redirect
import re
from django.utils.html import escape


def index(request, id=-1):
    if not request.user.is_authenticated:
        dir_tree = ''
        file_content = ''
        return render(request, 'utils/base.html')

    dirs = Directory.objects.all().filter(parent_dir=None, owner=request.user)

    return render(request, 'utils/base.html', {
        'files' : File.objects.all(),
        'directories' : Directory.objects.all(),
        'currentDir' : None,
    })

def add_dir(request, id=-1):

    if request.method == 'POST':
        name = request.POST.get('dir_name')
        desc = request.POST.get('dir_desc')
        user = request.user
        id = int(request.POST.get('dest_for_dir'))

        parent_set = Directory.objects.all().filter(id=id)

        if id == -1:
            new_dir = Directory(name=name, description=desc, owner=user)
        elif parent_set.exists():
            dir = parent_set[0]
            if dir.availability_flag == False:
                return redirect("/")

            new_dir = Directory(name=name, description=desc, owner=user, parent_dir=parent_set[0])
        else:
            return redirect('/')
    
        new_dir.save()

        context = {
            'id' : new_dir.id,
        }

        return redirect('/')

    else:
        return redirect('/')

def add_file(request, id=-1):

    if request.method == 'POST':
        name = request.POST.get('file_name')
        desc = request.POST.get('file_desc')
        f = request.FILES.get('file_file')
        user = request.user
        id = int(request.POST.get('dest_for_file'))

        parent_set = Directory.objects.all().filter(id=id)

        if id == -1:
            new_file = File(name=name, description=desc, owner=user, content=f)
        elif parent_set.exists():
            dir = parent_set[0]
            if dir.availability_flag == False:
                return redirect("/")

            new_file = File(name=name, description=desc, owner=user, parent_dir=parent_set[0], content=f)
        else:
            return redirect('/')

        new_file.save()

        context = {
            'id' : new_file.id
        }

        return redirect('/')

    else:
        return redirect('/')

def delete_all(root_dir):
    dirs = Directory.objects.all().filter(parent_dir=root_dir)

    for dir in dirs:
        dir.availability_flag = False
        dir.save()

        delete_all(dir)

    files = File.objects.all().filter(parent_dir=root_dir)

    for file in files:
        file.availability_flag = False
        file.save()

def delete(request):
    
    if request.method == 'POST':
        id = request.POST.get("to_delete")
        
        dir = Directory.objects.all().filter(id=id)

        if dir.exists():
            d = dir[0]
            d.availability_flag = False
            d.save()

            delete_all(dir[0])

            return redirect("/")

        file = File.objects.all().filter(id=id)

        if file.exists():
            f = file[0]
            f.availability_flag = False
            f.save()
            return redirect("/")

        return redirect("/")
    else:
        return redirect('/')