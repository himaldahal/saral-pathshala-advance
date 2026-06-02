from django.core.cache import cache
from django.utils import timezone
from .models import SiteSetting
from apps.exam.models import Exam

def site_settings(request):
    """
    Exposes the cached SiteSetting singleton to all templates.
    """
    cached_settings = cache.get('site_settings_cached')
    if not cached_settings:
        cached_settings = SiteSetting.objects.first()
        if not cached_settings:
            # Create a default settings object if none exists
            cached_settings = SiteSetting.objects.create(
                site_name="Saral Pathshala",
                site_title="Saral Pathshala - Online MCQ & Lectures Portal",
                contact_email="info@saralpathshala.com",
                contact_phone="9841234567"
            )
        cache.set('site_settings_cached', cached_settings, 86400) # cache for 24 hours
        
    from django.conf import settings
    
    # Fetch upcoming exams for the global sidebar
    upcoming_exams_sidebar = cache.get('upcoming_exams_sidebar')
    if not upcoming_exams_sidebar:
        upcoming_exams_sidebar = list(Exam.objects.filter(
            is_active=True,
            start_date__gte=timezone.now()
        ).select_related('course').order_by('start_date')[:5])
        cache.set('upcoming_exams_sidebar', upcoming_exams_sidebar, 60) # cache for 1 minute
        
    return {
        'site_settings': cached_settings,
        'recaptcha_site_key': getattr(settings, 'RECAPTCHA_SITE_KEY', ''),
        'upcoming_exams_sidebar': upcoming_exams_sidebar
    }
