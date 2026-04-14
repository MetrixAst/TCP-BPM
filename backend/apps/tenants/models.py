from django.db import models
from project.utils import PathAndRename
from datetime import date

class Room(models.Model):
    number = models.CharField("Номер помещения", max_length=30)
    map_id = models.CharField("Идентификатор на карте", max_length=30)
    floor = models.IntegerField("Этаж")

    def __str__(self):
        return self.number

    class Meta:
        verbose_name = "Помещение"
        verbose_name_plural = "Помещения"
        ordering = ['number']


class TenantCategory(models.Model):
    title = models.CharField("Заголовок", max_length=40)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Категория арендаторов"
        verbose_name_plural = "Категории арендаторов"
        ordering = ['title']


class Tenant(models.Model):

    INCREASE_TYPES = [
        ('step', 'Ступенчатая'),
        ('percent', 'Процентная'),
    ]

    name = models.CharField("Название", max_length=120)
    category = models.ForeignKey(TenantCategory, verbose_name="Категория", on_delete=models.SET_NULL, null=True, blank=False)
    room = models.ForeignKey(Room, verbose_name="Помещение", null=True, blank=False, on_delete=models.SET_NULL, related_name="tenant")

    note = models.TextField("Примечание", max_length=300, null=True, blank=True)

    area = models.FloatField("Площадь")
    price = models.FloatField("Ставка за кв2")

    discount = models.IntegerField("Скидка", default=0)

    phone = models.CharField("Номер телефона", max_length=40)
    email = models.EmailField("Email", max_length=40)
    address = models.CharField("Адрес", max_length=100)
    contact = models.CharField("Ответсвенное лицо", max_length=40)


    start_date = models.DateField("Начало аренды", null=True, blank=False)
    end_date = models.DateField("Завершение аренды", null=True, blank=False)
    discount_date = models.DateField("Срок скидки", null=True, blank=False)
    percent = models.SmallIntegerField("Процент с оборота", default=0)
    increase_type = models.SlugField("Повышение ставки", choices=INCREASE_TYPES, null=True, blank=False)

    image = models.ImageField("Фотография", upload_to=PathAndRename("tenants/"), null=True, blank=True)
    icon = models.ImageField("Иконка на карте", upload_to=PathAndRename("tenant_icons/"), null=True, blank=True)

    date_notify = models.DateTimeField(verbose_name="Дата уведомления о сроке", null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Арендатор"
        verbose_name_plural = "Арендаторы"
        ordering = ['name']

    @property
    def number(self):
        if self.room is not None:
            return self.room.number
        
        return "--"

    def get_image_url(self):
        if self.image:
            return self.image.url
        return "/static/site/img/profile/profile-11.webp"
    
    @property
    def days(self):
        today = date.today()
        days = (self.end_date - today).days

        return days

    @property
    def status(self):
        days = self.days
        
        if days >= 150:
            return 'green'
        elif days >= 90:
            return 'yellow'
        else:
            return 'red'
    
    def to_json(self):

        icon = None
        if self.icon.name != "":
            icon = self.icon.url

        return {
            "id": self.id,
            "map_id": self.room.map_id,
            "title": self.name,
            "class": None,
            "floor": self.room.floor,
            "icon": icon,
        }
