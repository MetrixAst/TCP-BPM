from django.db import models
from django.db.models import Q
from django.http import Http404
from mptt.models import MPTTModel, TreeForeignKey

from .enums import DocumentStatusEnum, DocumentTypeEnum
from account.models import UserAccount, Notification
from project.utils import get_or_error, get_or_none, PathAndRename

from purchases.models import Supplier


class Folder(MPTTModel):


    ROOT_TYPES = DocumentTypeEnum.list()

    name = models.CharField(max_length=50, unique=True)
    parent = TreeForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    root_type = models.SlugField("Тип папки (только для корневых)", choices=ROOT_TYPES, null=True, blank=True, unique=True)
    multiple_files = models.BooleanField("Несколько файлов в одном документе", default=False)

    @staticmethod
    def get_by_root_type(type, include_self=False):
        try:
            root = get_or_none(Folder, root_type=type)
            if root is not None:
                res = root.get_descendants(include_self=include_self)
                if not include_self:
                    res = res.filter(children__isnull=True)

                return res
            return Folder.objects.all()
        except:
            return None
        

    def __str__(self):
        return self.name

    class MPTTMeta:
        order_insertion_by = ['name']
    
    class Meta:
        verbose_name = "Папка"
        verbose_name_plural = "Папки"



class Document(models.Model):

    STATUSES = DocumentStatusEnum.list()
    DOCUMENT_TYPES = DocumentTypeEnum.list()
    
    document_type = models.SlugField("Тип документа", choices=DOCUMENT_TYPES)
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, related_name="documents", verbose_name="Папка")
    author = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, related_name="created_documents", verbose_name="Автор", null=True, blank=True)
    coordinators = models.ManyToManyField(UserAccount, related_name="coordinator_documents", verbose_name="Согласующие")
    observers = models.ManyToManyField(UserAccount, related_name="observe_documents", verbose_name="Наблюдатели")
    reg_date = models.DateField(verbose_name="Дата заполнения", null=True, blank=False)

    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")
    end_date = models.DateTimeField(verbose_name="Дата завершения", null=True)
    status = models.SlugField("Статус", choices=STATUSES)

    title = models.CharField("Заголовок", max_length=120, null=True, blank=False)
    number = models.CharField("Рег. №", max_length=120)
    text = models.TextField("Текст", max_length=2000, null=True, blank=True)

    document = models.FileField("Документ", upload_to=PathAndRename("documents/"), null=True, blank=True)

    need_all = models.BooleanField("Все должны согласовать", default=True, blank=True)
    need_head = models.BooleanField("Требуется подпись главы", default=True, blank=True)

    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, verbose_name="Контрагент", null=True, blank=False)

    date_notify = models.DateTimeField(verbose_name="Дата уведомления о сроке", null=True, blank=True)

    @staticmethod
    def get_available_queryset(request):
        queryset = Document.objects.filter(
            Q(author=request.user) | 
            Q(coordinators=request.user) | 
            Q(observers=request.user)
        )

        return queryset.distinct()
    
    @staticmethod
    def get_by_id(request, id, exception = True):
        
        qs = Document.get_available_queryset(request).filter(pk=id)
        if qs.count() > 0:
            if exception:
                return get_or_error(Document, id=id)
            return get_or_none(Document, id=id)
        else:
            if exception:
                raise Http404
            return None
        
    def get_status_notification(self):
        return DocumentStatusEnum.get_notification_text(self.status, self.document_type)

    @property
    def status_info(self):
        return DocumentStatusEnum.get_info(self.status, self.document_type)
    
    def actions(self, request):
        #TODO check can action
        return DocumentStatusEnum.get_actions(self.status, self.document_type)
    
    def set_action(self, request, action, text = ''):
        actions = self.actions(request)
        if action == "confirm":
            confirm_action = next((item for item in actions if item["action"] == "confirm"), None)
            if confirm_action is not None:
                self.status = confirm_action['next']
        elif action == "create":
            # if self.document_type == 'purchases':
            #     self.status = DocumentStatusEnum.OFFER.value[0]
            # else:
            self.status = DocumentStatusEnum.DRAFT.value[0]
            
        self.save()
        DocumentHistory.objects.create(document=self, user=request.user, status=self.status, text=text)

        #TODO add notification
        Notification.create_for_document(self)


    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ['-id']



class InnerDocument(models.Model):
    parent = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, related_name="inner_documents", verbose_name="Основной документ")
    author = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, verbose_name="Автор", null=True, blank=True)
    title = models.CharField("Заголовок", max_length=120, null=True, blank=False)
    document = models.FileField("Документ", upload_to=PathAndRename("inner_documents/"), null=True, blank=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Дополнительный документ"
        verbose_name_plural = "Дополнительные документы"
        ordering = ['-id']



class DocumentHistory(models.Model):

    STATUSES = DocumentStatusEnum.list()

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="history", verbose_name="Документ")
    user = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, verbose_name="Пользователь", null=True, blank=True)
    status = models.SlugField("Статус", choices=STATUSES)
    text = models.TextField("Комментарии", null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")


    @property
    def title(self):
        res = DocumentStatusEnum.from_value(self.status)
        if res is not None:
            return res[1]
        return ""

    def __str__(self):
        return self.document.title

    class Meta:
        verbose_name = "Активность"
        verbose_name_plural = "Активность"
        ordering = ['-id']