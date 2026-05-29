import os
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage

@csrf_exempt  # TinyMCE might not send the CSRF token by default
def upload_image(request):
    if request.method == 'POST' and request.FILES.get('file'):
        file_obj = request.FILES['file']
        # Save the file using Django's storage system
        file_path = default_storage.save(os.path.join('tinymce_uploads', file_obj.name), file_obj)
        file_url = settings.MEDIA_URL + file_path
        
        # Return the location to TinyMCE
        return JsonResponse({'location': file_url})
    
    return JsonResponse({'error': 'Failed to upload image'}, status=400)