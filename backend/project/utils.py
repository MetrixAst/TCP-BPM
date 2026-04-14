import os
import string    
import random # define the random module 

from django.http import Http404
from django.utils.deconstruct import deconstructible
from uuid import uuid4

def get_or_none(classmodel, **kwargs):
    try:
        return classmodel.objects.get(**kwargs)
    except classmodel.DoesNotExist:
        return None

def get_or_create(classmodel, **kwargs):
    try:
        qs = classmodel.objects.filter(**kwargs)
        if qs.count() > 0:
            return qs.first()
        return classmodel.objects.create(**kwargs)
    except classmodel.DoesNotExist:
        return None

def get_or_error(classmodel, **kwargs):
    try:
        return classmodel.objects.get(**kwargs)
    except classmodel.DoesNotExist:
        raise Http404

def get_random_string():
    S = 10
    ran = ''.join(random.choices(string.ascii_uppercase + string.digits, k = S))    
    return str(ran)

# Переименовывает файл картинки перед сохранением
@deconstructible
class PathAndRename(object):
    def __init__(self, sub_path):
        self.path = sub_path

    def __call__(self, instance, filename):
        ext = filename.split('.')[-1]
        # get filename
        filename = '{}.{}'.format(uuid4().hex, ext)
        return os.path.join(self.path, filename)