from django.contrib import admin
from .models import ESignerSigning


@admin.register(ESignerSigning)
class ESignerSigningAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "status", "esigner_document_id", "updated_at")
    list_filter = ("status", "content_type")
    readonly_fields = ("esigner_document_id", "esigner_folder_id", "sign_hash", "created_at", "updated_at")