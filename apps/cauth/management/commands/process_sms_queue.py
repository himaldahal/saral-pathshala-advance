import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings as dj_settings
from apps.cauth.models import SMSQueue, QueueStatus
from apps.pages.models import SiteSetting
from django.core.cache import cache

class Command(BaseCommand):
    help = "Processes the pending SMS queue using Aakash SMS gateway"

    def handle(self, *args, **options):
        site_settings = cache.get('site_settings_cached')
        if not site_settings:
            site_settings = SiteSetting.objects.first()
            if site_settings:
                cache.set('site_settings_cached', site_settings, 0)
        
        auth_token = site_settings.akash_sms_auth_token if site_settings else None
        
        is_token_missing = not auth_token or auth_token == "YOUR_AKASH_SMS_TOKEN"
        if is_token_missing and not dj_settings.DEBUG:
            self.stdout.write(self.style.ERROR("Aakash SMS Auth Token is not configured in Site Settings."))
            return

        pending_sms = SMSQueue.objects.filter(status=QueueStatus.PENDING)[:20]
        if not pending_sms.exists():
            self.stdout.write(self.style.SUCCESS("No pending SMS to process."))
            return

        # ✅ Fix 1: Correct v3 endpoint
        api_url = "https://sms.aakashsms.com/sms/v3/send"

        for sms in pending_sms:
            self.stdout.write(f"Sending SMS to {sms.to_phone}...")
            
            if dj_settings.DEBUG:
                self.stdout.write(self.style.WARNING("=== [DEVELOPMENT SMS LOG] ==="))
                self.stdout.write(self.style.WARNING(f"To: {sms.to_phone}"))
                self.stdout.write(self.style.WARNING(f"Message: {sms.message}"))
                self.stdout.write(self.style.WARNING("============================="))

            if is_token_missing and dj_settings.DEBUG:
                sms.mark_sent()
                self.stdout.write(self.style.SUCCESS(f"Successfully marked SMS to {sms.to_phone} as sent in development mode."))
                continue

            payload = {
                'auth_token': auth_token,
                'to': sms.to_phone,
                'text': sms.message,
            }
            try:
                response = requests.post(api_url, data=payload, timeout=10)
                response.raise_for_status()  # catch 4xx/5xx HTTP errors

                data = response.json()

                if not data.get('error', True):
                    sms.mark_sent()
                    self.stdout.write(self.style.SUCCESS(
                        f"Successfully sent SMS to {sms.to_phone}. "
                        f"Message: {data.get('message', '')}"
                    ))
                else:
                    error_msg = data.get('message', 'Unknown API error')
                    sms.mark_failed(f"API Error: {error_msg}")
                    self.stdout.write(self.style.WARNING(
                        f"Failed to send SMS to {sms.to_phone}: {error_msg}"
                    ))
                    
            except requests.exceptions.HTTPError as e:
                sms.mark_failed(f"HTTP Error: {str(e)}")
                self.stdout.write(self.style.ERROR(f"HTTP error for {sms.to_phone}: {str(e)}"))
            except requests.exceptions.RequestException as e:
                sms.mark_failed(str(e))
                self.stdout.write(self.style.ERROR(f"Request exception for {sms.to_phone}: {str(e)}"))
            except Exception as e:
                sms.mark_failed(str(e))
                self.stdout.write(self.style.ERROR(f"Unexpected error for {sms.to_phone}: {str(e)}"))