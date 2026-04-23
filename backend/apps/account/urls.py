from django.urls import path, include
from . import views


urlpatterns = [
    path('auth', views.CustomLoginView.as_view(), name="auth"),
    path('guest', views.GuestView.as_view(), name="guest"),
    
    path('logout', views.CustomLogoutView.as_view(), name="logout"),
    
    path('profile', views.profile_view, name="profile"),
    path('notifications', views.notifications_view, name="notificaitons"),
    path('notification_indicator/<int:target_id>/<str:target_type>', views.indicator_readed, name="notification_readed"),

    path('structure/<str:get>', views.structure_csv, name="structure"),
    path('ajax/users/<str:selection>', views.users_ajax, name="users"),


    path("mobile/auth", views.auth, name="auth_mobile"),
    path("mobile/side_menu", views.get_side_menu, name="side_menu_mobile"),
    path("mobile/push_token", views.push_token, name="push_token_mobile"),

]