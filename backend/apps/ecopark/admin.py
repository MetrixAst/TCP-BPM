from django.contrib import admin
from .models import EcoObject, EcoExecutor, EcoWork

admin.site.register(EcoObject)
admin.site.register(EcoExecutor)
admin.site.register(EcoWork)