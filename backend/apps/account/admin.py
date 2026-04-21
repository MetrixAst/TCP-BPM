from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django_mptt_admin.admin import DjangoMpttAdmin
from .models import UserAccount, Department, Employee, Notification, PushToken
from .forms import EmployeeAdminForm


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
    model = Employee
    fields = ('user', 'iin', 'status', 'supervisor', 'head') 
    autocomplete_fields = ('user', 'supervisor') 
    extra = 1


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

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    form = EmployeeAdminForm
    list_display = ('user', 'department', 'position', 'status', 'iin', 'head')
    
    list_filter = ('status', 'department', 'position', 'head')
    
    search_fields = ('user__username', 'user__last_name', 'iin', 'phone')

    autocomplete_fields = ('user', 'supervisor', 'position')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'department', 'position', 'status', 'head')
        }),
        ('Личные данные', {
            'fields': ('iin', 'hire_date', 'phone', 'personal_email')
        }),
        ('Иерархия', {
            'fields': ('supervisor',)
        }),
    )

