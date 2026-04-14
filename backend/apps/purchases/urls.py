from django.urls import path, include
from . import views

urlpatterns = [
    # path('', views.purchases, name="home"),
    # path('item/<int:pk>', views.purchase_item, name="item"),
    # path('item/<int:pk>/edit', views.edit_item, name="edit"),

    path('suppliers', views.suppliers, name="suppliers"),
    path('suppliers/<slug:status>', views.suppliers_by_status, name="suppliers_by_status"),
    path('supplier/<int:pk>', views.supplier, name="supplier"),
    path('supplier/<int:pk>/edit', views.edit_supplier, name="edit_supplier"),
]