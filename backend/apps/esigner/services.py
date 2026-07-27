import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .client import ESignerClient
from .models import ESignerSigning

logger = logging.getLogger(__name__)


def send_for_signing(obj, file_field_name: str, signers: list, company_id: int = None) -> ESignerSigning:
    client = ESignerClient()
    company_id = company_id or settings.ESIGNER_COMPANY_ID
    folder_id = settings.ESIGNER_FOLDER_ID

    file_field = getattr(obj, file_field_name)
    if not file_field:
        raise ValueError(f"{obj} не имеет файла в поле '{file_field_name}'")

    content_type = ContentType.objects.get_for_model(obj)
    with transaction.atomic():
        existing = ESignerSigning.objects.select_for_update().filter(
            content_type=content_type,
            object_id=obj.pk,
        ).first()
        if existing and existing.status not in (
            ESignerSigning.STATUS_ARCHIVED,
            ESignerSigning.STATUS_REVOKED,
        ):
            raise ValueError("Документ уже отправлен на подписание")

        with file_field.open("rb") as f:
            uploaded = client.upload_document(
                folder_id, file_field.name.split("/")[-1], f, "application/octet-stream",
            )

        signing, _ = ESignerSigning.objects.update_or_create(
            content_type=content_type,
            object_id=obj.pk,
            defaults={
                "esigner_document_id": uploaded["id"],
                "esigner_folder_id": folder_id,
                "sign_hash": "",
                "signed_pdf": None,
                "status": ESignerSigning.STATUS_DRAFT,
                "signers": signers,
            },
        )

        for signer in signers:
            client.add_signer(uploaded["id"], signer["bin_or_iin"], signer["is_company"])

        sent = client.send_for_signing(uploaded["id"])
        signing.sign_hash = sent["hash"]
        signing.status = ESignerSigning.STATUS_SENT
        signing.save(update_fields=["sign_hash", "status"])

    logger.info("%s#%s sent to eSigner, sign_url=%s", content_type, obj.pk, signing.sign_url)
    return signing


def handle_webhook(payload: dict):
    if payload.get("status") != "COMPLETED":
        return False

    esigner_document_id = payload.get("document_id")
    if not esigner_document_id:
        logger.warning("eSigner webhook without document_id")
        return False

    with transaction.atomic():
        try:
            signing = ESignerSigning.objects.select_for_update().select_related(
                "content_type"
            ).get(esigner_document_id=esigner_document_id)
        except ESignerSigning.DoesNotExist:
            logger.warning("eSigner webhook for unknown document_id=%s", esigner_document_id)
            return False

        if signing.status == ESignerSigning.STATUS_COMPLETED:
            return True

        client = ESignerClient()
        doc_data = client.get_document(esigner_document_id)
        if doc_data.get("status") != "COMPLETED":
            return False

        from django.core.files.base import ContentFile
        pdf_bytes = client.download_signed_pdf(esigner_document_id)
        signing.signed_pdf.save(f"{esigner_document_id}.pdf", ContentFile(pdf_bytes), save=False)
        signing.status = ESignerSigning.STATUS_COMPLETED
        signing.save(update_fields=["signed_pdf", "status"])
        _apply_post_signing_hook(signing)
        return True


def _apply_post_signing_hook(signing: ESignerSigning):
    model_label = f"{signing.content_type.app_label}.{signing.content_type.model}"
    obj = signing.content_object
    if obj is None:
        return

    if model_label == "documents.document":
        from documents.enums import DocumentStatusEnum
        from documents.models import DocumentHistory
        from account.models import Notification

        obj.status = DocumentStatusEnum.ACTIVE.value[0]
        obj.save(update_fields=["status"])

        DocumentHistory.objects.create(
            document=obj, user=None, status=obj.status,
            text="Документ подписан через eSigner",
        )
        Notification.create_for_document(obj)

    elif model_label == "requistions.requistion":
        from requistions.enums import RequstionStatusEnum
        from requistions.models import RequistionHistory
        from requistions.services import notify_requisition_status

        obj.status = RequstionStatusEnum.ACTIVE.value[0]
        obj.save(update_fields=["status"])

        RequistionHistory.objects.create(
            requistion=obj, user=None, status=obj.status,
            text="Документ подписан через eSigner",
        )
        notify_requisition_status(obj)

    elif model_label == "hr.employeedocument":
        from datetime import date
        from hr.enums import DocumentStatusEnum as HRDocStatusEnum

        obj.status = HRDocStatusEnum.ACTIVE
        obj.signed_at = date.today()
        obj.save(update_fields=["status", "signed_at"])

    elif model_label == "hr.employeecertification":
        pass  

    elif model_label == "hr.employeeworkpermit":
        pass 


def poll_pending_signings():
    client = ESignerClient()
    pending = ESignerSigning.objects.filter(status=ESignerSigning.STATUS_SENT)
    for signing in pending:
        try:
            data = client.get_document(signing.esigner_document_id)
        except Exception:
            logger.exception("Poll failed for signing %s", signing.pk)
            continue
        if data.get("status") == "COMPLETED":
            handle_webhook({"document_id": signing.esigner_document_id, "status": "COMPLETED"})
        elif data.get("status") in ("REVOKED", "ARCHIVED"):
            signing.status = data["status"]
            signing.save(update_fields=["status"])