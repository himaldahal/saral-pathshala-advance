from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    
    path('courses/', views.course_list, name='course_list'),
    path('course/<slug:slug>/', views.course_detail, name='course_detail'),
    path('course/<slug:slug>/enroll-instantly/', views.enroll_instantly, name='enroll_instantly'),
    path('enroll-request/', views.enroll_request, name='enroll_request'),
    
    path('course/lecture/<int:lecture_id>/', views.lecture_detail, name='lecture_detail'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    path('notices/', views.notice_list, name='notice_list'),
    path('notice/<slug:slug>/', views.notice_detail, name='notice_detail'),
    
    # Custom Staff & Admin Dashboards / Tools
    path('dhokakhol-custom/import-enrollments/', views.admin_import_enrollments, name='admin_import_enrollments'),
    path('dhokakhol-custom/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('dhokakhol-custom/export-results/<int:exam_id>/', views.admin_export_exam_results, name='admin_export_exam_results'),
    path('dhokakhol-custom/manage-enrollment-request/<int:request_id>/<str:action>/', views.admin_manage_enrollment_request, name='admin_manage_enrollment_request'),
    path('dhokakhol-custom/api/get-sections-paragraphs/', views.admin_api_get_sections_paragraphs, name='admin_api_get_sections_paragraphs'),
    path('dhokakhol-custom/api/get-question-difficulty/', views.admin_api_get_question_difficulty, name='admin_api_get_question_difficulty'),
    
    # Custom CRUD for Exams, Sections and Passages
    path('dhokakhol-custom/manage-exam/', views.admin_manage_exam, name='admin_create_exam'),
    path('dhokakhol-custom/manage-exam/<int:exam_id>/', views.admin_manage_exam, name='admin_edit_exam'),
    path('dhokakhol-custom/delete-exam/<int:exam_id>/', views.admin_delete_exam, name='admin_delete_exam'),
    path('dhokakhol-custom/manage-sections/<int:exam_id>/', views.admin_manage_sections, name='admin_manage_sections'),
    path('dhokakhol-custom/manage-sections/<int:exam_id>/delete/<int:section_id>/', views.admin_delete_section, name='admin_delete_section'),
    path('dhokakhol-custom/manage-paragraphs/<int:section_id>/', views.admin_manage_paragraphs, name='admin_manage_paragraphs'),
    path('dhokakhol-custom/manage-paragraphs/<int:section_id>/delete/<int:paragraph_id>/', views.admin_delete_paragraph, name='admin_delete_paragraph'),
    
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),

    path('robots.txt', views.robots_txt, name='robots_txt'),
]