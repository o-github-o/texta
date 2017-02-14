import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User, Group, Permission
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.template import loader

from permission_admin.models import Dataset
from utils.es_manager import ES_Manager

from texta.settings import STATIC_URL, URL_PREFIX

import datetime


# new group to assign model run permissions to users
#modelrun_group = Group.objects.get_or_create(name='change_modelrun')[0]
#change_modelrun = Permission.objects.get(name='Can change model run')
#modelrun_group.permissions.add(change_modelrun)
#modelrun_group.save()

@login_required
@user_passes_test(lambda u: u.is_superuser)
def add_dataset(request):
    daterange = json.dumps({'min':request.POST['daterange_from'],'max':request.POST['daterange_to']})
    Dataset(author=request.user, index=request.POST['index'], mapping=request.POST['mapping'], daterange=daterange).save()
    return HttpResponseRedirect(URL_PREFIX + '/permission_admin/')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_dataset(request):
    index_to_delete = request.POST['index']
    index_to_delete = Dataset.objects.get(pk = index_to_delete)
    index_to_delete.delete()
    return HttpResponseRedirect(URL_PREFIX + '/permission_admin/')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def index(request):
    datasets = Dataset.objects.all()
    users = get_user_fields()
    indices = ES_Manager.get_indices()
    template = loader.get_template('permission_admin.html')
    return HttpResponse(template.render({'users':users,'datasets':datasets,'indices':indices,'STATIC_URL':STATIC_URL,'URL_PREFIX':URL_PREFIX},request))

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_user(request):
    username_to_delete = request.POST['username']
    user_to_delete = User.objects.get(username = username_to_delete)
    user_to_delete.delete()
    return HttpResponseRedirect(URL_PREFIX + '/permission_admin/')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def save_permissions(request):
    usernames = get_usernames()
    new_superusers = request.POST.getlist('superuser')
#    new_chmodelrun_users = request.POST.getlist('change_modelrun')

    for username in usernames:
        user = User.objects.get(username=username)
        if username in new_superusers:
            user.is_superuser = True
        else:
            user.is_superuser = False

#        if username in new_chmodelrun_users:
#            user.groups.add(modelrun_group)
#        else:
#            user.groups.remove(modelrun_group)

        user.save()
#        modelrun_group.save()
    return HttpResponseRedirect(URL_PREFIX + '/permission_admin/')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def get_mappings(request):
    index = request.GET['index']
    print(ES_Manager.get_mappings(index))
    return HttpResponse(json.dumps(ES_Manager.get_mappings(index)))

def get_user_fields():
    user_objects = User.objects.all()
    users = []
    for user in user_objects:
        user_fields = {'username': user.username}

        if user.is_superuser:
            user_fields['superuser'] = 1
        else:
            user_fields['superuser'] = 0

#        if user.groups.filter(name='change_modelrun').exists():
#            user_fields['change_modelrun'] = 1
#        else:
#            user_fields['change_modelrun'] = 0

        user_fields['last_login'] = user.last_login
        user_fields['e_mail'] = user.email

        users.append(user_fields)
    users = sorted(users, key=lambda u: u['last_login'] if u['last_login'] else datetime.datetime(year=1900,month=1,day=1), reverse=True)
    return users

def get_usernames():
    users = User.objects.all()
    usernames = []
    for user in users:
        usernames.append(user.username)
    return usernames