from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from .file_upload import upload_image

urlpatterns = [
    path('auth/',include('apps.cauth.urls')),
    path('',include('apps.pages.urls')),
    path('tinymce/', include('tinymce.urls')),
    path('exams/',   include('apps.exam.urls', namespace='exams')),
    path('dhokakhol/', admin.site.urls),
    path('astabakraa/sp/upload_images/', upload_image, name='tinymce_upload_image'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'apps.pages.views.handler404'
handler500 = 'apps.pages.views.handler500'