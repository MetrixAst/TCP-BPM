from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django_mptt_admin.admin import DjangoMpttAdmin
from .models import UserAccount, Department, Employee, Notification, PushToken


class CustomUserAdmin(UserAdmin):

    search_fields = ('username', )
    
    list_display = (
        'username', 'role', 'gender',
        )

    fieldsets = (
        (None, {
            'fields': ('username', 'password', 'role')
        }),
        ('Additional info', {
            'fields': ('birthday', 'gender', 'avatar')
        }),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'email')
        }),
    )

    add_fieldsets = (
        (None, {
            'fields': ('username', 'password1', 'password2', 'role')
        }),
    )

admin.site.register(UserAccount, CustomUserAdmin)


class EmployeeInline(admin.TabularInline):
    autocomplete_fields = ('user', )
    model = Employee


class DepartmentA(DjangoMpttAdmin):
    inlines=[EmployeeInline]
    tree_auto_open = 0

admin.site.register(Department, DepartmentA)



@admin.register(PushToken)
class PushTokenA(admin.ModelAdmin):
    readonly_fields = ('user', 'fcm', )
    search_fields = ('user__username', )

@admin.register(Notification)
class NotificationA(admin.ModelAdmin):
    list_display = ('title', 'text', 'created_date', 'sended')
    autocomplete_fields = ('users', )
    # inlines = (GalleryImageInline, )