from django.contrib import admin
from .models import Country, City, SupplierCategory, Supplier

admin.site.register(Country)
admin.site.register(City)
admin.site.register(SupplierCategory)
admin.site.register(Supplier)
