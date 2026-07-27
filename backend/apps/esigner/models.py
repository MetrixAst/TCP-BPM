from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class ESignerSigning(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_SENT = "SENT"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_ARCHIVED = "ARCHIVED"
    STATUS_REVOKED = "REVOKED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Черновик"),
        (STATUS_SENT, "Отправлен на подписание"),
        (STATUS_COMPLETED, "Подписан"),
        (STATUS_ARCHIVED, "Архив"),
        (STATUS_REVOKED, "Отозван"),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")

    esigner_document_id = models.CharField("ID документа в eSigner", max_length=64)
    esigner_folder_id = models.CharField("ID папки в eSigner", max_length=64)
    sign_hash = models.CharField("Хэш ссылки на подписание", max_length=64, blank=True)
    status = models.CharField("Статус", max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    signers = models.JSONField("Подписанты", default=list, blank=True)
    signed_pdf = models.FileField("Подписанный PDF", upload_to="esigner_signed/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def sign_url(self):
        if not self.sign_hash:
            return None
        from django.conf import settings
        return f"{settings.ESIGNER_SIGN_BASE_URL}/{self.sign_hash}"

    def __str__(self):
        return f"eSigner: {self.content_type}#{self.object_id} ({self.status})"

    class Meta:
        verbose_name = "Подписание eSigner"
        verbose_name_plural = "Подписания eSigner"
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id"], name="unique_esigner_signing_per_object"
            )
        ]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]