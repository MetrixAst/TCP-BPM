from django.contrib import admin
from django_mptt_admin.admin import DjangoMpttAdmin
from .models import Folder, Document

class FolderA(DjangoMpttAdmin):
    tree_auto_open = 0
    list_display = ('name', 'root_type', 'access_scope')
    raw_id_fields = ('access_scope',)

admin.site.register(Folder, FolderA)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'document_type', 'author', 'status', 'access_scope', 'date')
    list_filter = ('document_type', 'status')
    search_fields = ('number', 'title')
    raw_id_fields = ('author', 'folder', 'access_scope')
    filter_horizontal = ('coordinators', 'observers')