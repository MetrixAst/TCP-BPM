from django.db import models
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import Http404

from project.utils import PathAndRename, get_or_error, get_or_none

from account.models import UserAccount
from purchases.models import Supplier

from .enums import RequstionStatusEnum, RequstionTypesEnum

class Requistion(models.Model):

    STATUSES = RequstionStatusEnum.list()
    TYPES = RequstionTypesEnum.list()
    
    requistion_type = models.SlugField("Тип заявки", choices=TYPES)
    user = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, related_name="requistions", verbose_name="Пользователь", null=True, blank=True)

    coordinators = models.ManyToManyField(UserAccount, related_name="coordinator_requistions", verbose_name="Согласующие")
    observers = models.ManyToManyField(UserAccount, related_name="observe_requistions", verbose_name="Наблюдатели")

    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, verbose_name="Контрагент", null=True, blank=False)
    status = models.SlugField("Статус", choices=STATUSES)

    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")
    number = models.CharField("Рег. №", max_length=120, null=True, blank=True)


    #INFO ITEMS
    room = models.CharField("Помещение №", max_length=20, null=True, blank=False)
    route = models.CharField("Маршрут", max_length=100, null=True, blank=False)
    prop_list = models.TextField("Список имущества", null=True, blank=False)
    people_list = models.TextField("Список лиц", null=True, blank=False)

    start_date = models.DateField("Дата начала", null=True, blank=False)
    start_time = models.CharField("Время", max_length=20, null=True, blank=False)

    name = models.CharField("ФИО", max_length=50, null=True, blank=False)
    role = models.CharField("Должность", max_length=50, null=True, blank=False)
    phone = models.CharField("Телефон", max_length=50, null=True, blank=False)

    address = models.CharField("Адрес", max_length=50, null=True, blank=False)
    iin = models.CharField("ИИН", max_length=50, null=True, blank=False)


    def __str__(self):
        return f"Заявка № {self.id}"

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ['-id']



    @staticmethod
    def get_available_queryset(request):
        queryset = Requistion.objects.filter(
            Q(user=request.user) | 
            Q(coordinators=request.user) | 
            Q(observers=request.user)
        )

        return queryset.distinct()
    
    @staticmethod
    def get_by_id(request, id, exception = True):
        
        qs = Requistion.get_available_queryset(request).filter(pk=id)
        if qs.count() > 0:
            if exception:
                return get_or_error(Requistion, id=id)
            return get_or_none(Requistion, id=id)
        else:
            if exception:
                raise Http404
            return None

    @property
    def status_info(self):
        return RequstionStatusEnum.get_info(self.status, self.requistion_type)
    
    def actions(self, request):
        #TODO check can action
        return RequstionStatusEnum.get_actions(self.status, self.requistion_type, self.user, request.user)
    
    def set_action(self, request, action, text = ''):
        actions = self.actions(request)
        if action == "confirm":
            confirm_action = next((item for item in actions if item["action"] == "confirm"), None)
            if confirm_action is not None:
                self.status = confirm_action['next']
        elif action == "create":
            self.status = RequstionStatusEnum.DRAFT.value[0]
            
        self.save()
        RequistionHistory.objects.create(requistion=self, user=request.user, status=self.status, text=text)

        #TODO add notification

    def get_data(self):
        res = {
            'Идентификатор': self.id,
            'Тип заявки': self.get_requistion_type_display(),
            '№ заявки': self.number,
            'Пользователь': self.user.get_name,
            'Контрагент': str(self.supplier),
            'Статус': self.get_status_display(),
            'Дата заявки': self.date,
            'Помещение №': self.room,
            'Маршрут': self.route,
            'Список имущества': self.prop_list,
            'Список лиц': self.people_list,
            'Дата начала': self.start_date,
            'Время': self.start_time,
            'ФИО': self.name,
            'Должность': self.role,
            'Телефон': self.phone,
            'Адрес': self.address,
            'ИИН': self.iin,
        }

        return res


class RequistionHistory(models.Model):

    STATUSES = RequstionStatusEnum.list()

    requistion = models.ForeignKey(Requistion, on_delete=models.CASCADE, related_name="history", verbose_name="Заявка")
    user = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, verbose_name="Пользователь", null=True, blank=True)
    status = models.SlugField("Статус", choices=STATUSES)
    text = models.TextField("Комментарии", null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")


    @property
    def title(self):
        res = RequstionStatusEnum.from_value(self.status)
        if res is not None:
            return res[1]
        return ""

    def __str__(self):
        return self.requistion.requistion_type

    class Meta:
        verbose_name = "Активность заявки"
        verbose_name_plural = "Активность заявки"
        ordering = ['-id']