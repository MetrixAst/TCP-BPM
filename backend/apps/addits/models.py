from django.db import models
from account.models import UserAccount
from django.utils import timezone


class Comment(models.Model):
    
    target_id = models.IntegerField("Идентификатор")
    target_type = models.CharField("Тип", max_length=20)

    user = models.ForeignKey(UserAccount, on_delete=models.SET_NULL, verbose_name="Пользователь", null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True, verbose_name="Дата")

    text = models.TextField("Текст", max_length=1000)


    @staticmethod
    def create_comment(target_type, target_id, user, text):
        #TODO CHECK CAN ADD COMMENT
        return Comment.objects.create(target_type=target_type, target_id=target_id, user=user, text=text)

    @property
    def formatted_date(self):
        to_tz = timezone.get_default_timezone()
        return self.date.astimezone(to_tz).strftime('%d.%m.%Y %H:%M')

    def __str__(self):
        return self.text

    class Meta:
        verbose_name = "Комментарии"
        verbose_name_plural = "Комментарии"
        ordering = ['-id']