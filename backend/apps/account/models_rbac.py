from django.conf import settings
from django.db import models


class AppPermission(models.Model):

    code = models.SlugField("Код", max_length=64, unique=True)
    category = models.CharField("Категория", max_length=32, default="general")
    label = models.CharField("Название", max_length=128, blank=True)
    is_active = models.BooleanField("Активно", default=True)

    class Meta:
        app_label = "account"
        verbose_name = "Право доступа"
        verbose_name_plural = "Права доступа"
        ordering = ["category", "code"]

    def __str__(self):
        return f"{self.label or self.code} ({self.code})"


class PermissionProfile(models.Model):

    name = models.CharField("Название профиля", max_length=64, unique=True)
    role = models.SlugField("Роль", max_length=32, null=True, blank=True, unique=True)
    is_system = models.BooleanField("Системный профиль", default=False)
    description = models.CharField("Описание", max_length=255, blank=True)
    permissions = models.ManyToManyField(
        AppPermission,
        related_name="profiles",
        blank=True,
        verbose_name="Права",
    )

    class Meta:
        app_label = "account"
        verbose_name = "Профиль прав"
        verbose_name_plural = "Профили прав"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserPermissionOverride(models.Model):
    EFFECT_ALLOW = "ALLOW"
    EFFECT_DENY = "DENY"
    EFFECT_CHOICES = [
        (EFFECT_ALLOW, "Разрешить"),
        (EFFECT_DENY, "Запретить"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="permission_overrides",
        verbose_name="Пользователь",
    )
    permission = models.ForeignKey(
        AppPermission,
        on_delete=models.CASCADE,
        related_name="user_overrides",
        verbose_name="Право",
    )
    effect = models.CharField("Эффект", max_length=8, choices=EFFECT_CHOICES)
    reason = models.CharField("Причина", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Кем задано",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "account"
        verbose_name = "Индивидуальное право"
        verbose_name_plural = "Индивидуальные права"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "permission"],
                name="unique_user_permission_override",
            )
        ]

    def __str__(self):
        return f"{self.user_id}: {self.effect} {self.permission.code}"

class ProfileAssignment(models.Model):
    SCOPE_ROLE = "role"
    SCOPE_DEPARTMENT = "department"
    SCOPE_CHOICES = [
        (SCOPE_ROLE, "По роли"),
        (SCOPE_DEPARTMENT, "По отделу"),
    ]

    profile = models.ForeignKey(
        PermissionProfile,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Профиль прав",
    )
    scope_type = models.CharField(
        "Тип группы", max_length=16, choices=SCOPE_CHOICES
    )
    role = models.SlugField(
        "Роль", max_length=32, null=True, blank=True
    )
    department = models.ForeignKey(
        "account.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="profile_assignments",
        verbose_name="Отдел",
    )
    can_delegate = models.BooleanField(
        "Разрешена делегация", default=False,
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+",
        verbose_name="Кем назначено",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "account"
        verbose_name = "Назначение профиля"
        verbose_name_plural = "Назначения профилей"
        ordering = ["scope_type"]

    def __str__(self):
        if self.scope_type == self.SCOPE_ROLE:
            return f"{self.profile.name} → роль:{self.role}"
        return f"{self.profile.name} → отдел:{self.department}"