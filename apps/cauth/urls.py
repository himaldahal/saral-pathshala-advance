from django.urls import path
from . import views as auth_views

urlpatterns = [
    path('', auth_views.auth_home, name='auth_home'),
    path('login/', auth_views.aesthetic_login, name='login'),
    path('register/', auth_views.register, name='register'),
    path('verify-otp/', auth_views.verify_otp, name='verify_otp'),
    path('logout/', auth_views.u_logout, name='logout'),
    
    path('forgot-password/', auth_views.forgot_password, name='forgot_password'),
    path('reset-password/<uuid:token>/', auth_views.reset_password_confirm, name='reset_password_confirm'),
    path('verify-email/<uuid:token>/', auth_views.verify_email, name='verify_email'),
]