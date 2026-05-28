# urls.py example execution logic structure map:
from django.urls import path
from . import views as auth_views

urlpatterns = [
    path('login/', auth_views.aesthetic_login),
    path('register/', auth_views.register, name='register'),
    path('verify-otp/', auth_views.verify_otp, name='verify_otp'),
    path('', auth_views.aesthetic_login, name='login'), #as fall back mechanism
    path('logout/', auth_views.u_logout, name='logout'),
]