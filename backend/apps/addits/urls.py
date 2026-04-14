from django.urls import path, include
from account.role_permissions import need_permission, PermissionEnums
from . import views


urlpatterns = [
    path('comment/<str:target_type>/<int:target_id>', need_permission(PermissionEnums.COMMENT)(views.CommentView.as_view()), name="comment"),
]