from django.urls import path
from . import views

urlpatterns = [
    path('chat/', views.chat_view, name='chat'),
    path('login/', views.login_view, name='login'),
    path('panel/', views.panel_view, name='panel'),
    path('upload/', views.upload, name='upload'),
]
