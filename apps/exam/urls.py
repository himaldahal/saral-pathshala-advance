from django.urls import path
from . import views

app_name = 'exams'

urlpatterns = [
    path('',                          views.exam_list,         name='exam_list'),
    path('import/',                   views.import_exam_page,  name='import_exam_page'),
    path('import/upload/',            views.import_exam,       name='import_exam'),
    path('template/download/',        views.download_template, name='download_template'),
    path('<slug:slug>/',              views.exam_detail,       name='exam_detail'),
    path('<slug:slug>/start/',        views.start_exam,        name='start_exam'),
    path('<slug:slug>/attempt/',      views.exam_attempt,      name='exam_attempt'),
    path('<slug:slug>/save-answer/',  views.save_answer,       name='save_answer'),
    path('<slug:slug>/submit/',       views.submit_exam,       name='submit_exam'),
    path('<slug:slug>/result/',       views.exam_result,       name='exam_result'),
    path('<slug:slug>/delete-attempt/',views.delete_attempt,   name='delete_attempt'),
]