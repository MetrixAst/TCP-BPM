from django.contrib import admin
from django_mptt_admin.admin import DjangoMpttAdmin
from .models import Folder, Document

class FolderA(DjangoMpttAdmin):
    # inlines=[EmployeeInline]
    tree_auto_open = 0

admin.site.register(Folder, FolderA)

admin.site.register(Document)