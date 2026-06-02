from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.cauth.models import PhoneOTP, EmailToken, PasswordResetToken, SMSQueue, MailQueue

class Command(BaseCommand):
    help = "Flushes all OTPs, verification tokens, and completed queues older than 24 hours"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=24)
        
        # Delete security tokens older than 24 hours
        deleted_otps = PhoneOTP.objects.filter(created_at__lt=cutoff).delete()[0]
        deleted_emails = EmailToken.objects.filter(created_at__lt=cutoff).delete()[0]
        deleted_resets = PasswordResetToken.objects.filter(created_at__lt=cutoff).delete()[0]
        
        # Clear SMS and Mail queues older than 24 hours to save DB space
        deleted_sms = SMSQueue.objects.filter(created_at__lt=cutoff).delete()[0]
        deleted_mail = MailQueue.objects.filter(created_at__lt=cutoff).delete()[0]
        
        self.stdout.write(self.style.SUCCESS(
            f"Successfully flushed database elements older than 24 hours:\n"
            f"- Phone OTPs: {deleted_otps}\n"
            f"- Email Tokens: {deleted_emails}\n"
            f"- Reset Tokens: {deleted_resets}\n"
            f"- SMS Queue Logs: {deleted_sms}\n"
            f"- Mail Queue Logs: {deleted_mail}"
        ))
