from django.urls import path
from . import views

urlpatterns = [
    path('courses/', views.course_list, name='course_list'),
    path('course/lecture/<int:lecture_id>/', views.lecture_detail, name='lecture_detail'),
    path('dashboard/', views.dashboard, name='dashboard'),
]