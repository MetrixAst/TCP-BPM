from django.contrib import admin
from django_mptt_admin.admin import DjangoMpttAdmin
from .models import Folder, Document

class FolderA(DjangoMpttAdmin):
    tree_auto_open = 0
    list_display = ('name', 'root_type', 'access_scope')
    raw_id_fields = ('access_scope',)

admin.site.register(Folder, FolderA)

admin.site.register(Document)