"""project URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf.urls.static import static
from django.conf import settings
from django.contrib import admin
from django.urls import path, include

from django.conf.urls import handler403, handler404, handler500

handler403 = 'addits.views.custom_permission_denied_view'
handler404 = 'addits.views.custom_page_not_found_view'
handler500 = 'addits.views.custom_error_view'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('account/', include(('account.urls', 'account'))),
    path('doc/', include(('documents.urls', 'documents'))),
    path('ecopark/', include(('ecopark.urls', 'ecopark'))),
    path('finances/', include(('finances.urls', 'finances'))),
    path('onec/', include(('onec.urls', 'onec'))),
    path('hr/', include(('hr.urls', 'hr'))),
    path('purchases/', include(('purchases.urls', 'purchases'))),
    path('reports/', include(('reports.urls', 'reports'))),
    path('requistions/', include(('requistions.urls', 'requistions'))),
    path('tasks/', include(('tasks.urls', 'tasks'))),
    path('tenants/', include(('tenants.urls', 'tenants'))),
    path('addits/', include(('addits.urls', 'addits'))),
    path('', include(('dashboard.urls', 'dashboard'))),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)