from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from apps.cauth.models import PhoneOTP, EmailToken, PasswordResetToken, SMSQueue, MailQueue, QueueStatus

CLEANUP_CACHE_KEY = 'cron_cleanup_last_run'
CLEANUP_INTERVAL_SECONDS = 300  # Run heavy cleanup only every 5 minutes


class Command(BaseCommand):
    help = (
        "Unified cron command running every minute to process pending SMS, "
        "pending emails, and clear expired or used authentication/verification tokens."
    )

    def handle(self, *args, **options):
        self.stdout.write("--- Starting Unified Cron Task ---")

        # 1. SMS queue (every run)
        self.stdout.write("Dispatching pending SMS queue...")
        try:
            call_command('process_sms_queue')
            self.stdout.write(self.style.SUCCESS("SMS queue processing completed."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error executing process_sms_queue: {str(e)}"))

        # 2. Mail queue (every run)
        self.stdout.write("Dispatching pending mail queue...")
        try:
            call_command('process_mail_queue')
            self.stdout.write(self.style.SUCCESS("Mail queue processing completed."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error executing process_mail_queue: {str(e)}"))

        # 3. Cleanup — throttled via cache, runs every 5 minutes max
        last_run = cache.get(CLEANUP_CACHE_KEY)
        if last_run:
            self.stdout.write("Cleanup skipped (ran recently).")
            self.stdout.write("--- Unified Cron Task Completed ---")
            return

        self.stdout.write("Performing security tokens and expired records cleanup...")

        now = timezone.now()
        expired_cutoff = now - timedelta(hours=24)   # unused/expired older than 24h
        used_cutoff    = now - timedelta(minutes=10) # used tokens older than 10 min

        # ── OTPs ──────────────────────────────────────────────────────────────
        # Unused but expired beyond 24h
        deleted_expired_otps = PhoneOTP.objects.filter(
            is_used=False,
            expires_at__lt=expired_cutoff
        ).delete()[0]

        # Used, and used_at was more than 10 minutes ago
        deleted_used_otps = PhoneOTP.objects.filter(
            is_used=True,
            used_at__lt=used_cutoff        # ← correct field, not created_at
        ).delete()[0]

        # ── Email Tokens ──────────────────────────────────────────────────────
        deleted_expired_emails = EmailToken.objects.filter(
            is_used=False,
            expires_at__lt=expired_cutoff
        ).delete()[0]

        deleted_used_emails = EmailToken.objects.filter(
            is_used=True,
            used_at__lt=used_cutoff
        ).delete()[0]

        # ── Password Reset Tokens ─────────────────────────────────────────────
        deleted_expired_resets = PasswordResetToken.objects.filter(
            is_used=False,
            expires_at__lt=expired_cutoff
        ).delete()[0]

        deleted_used_resets = PasswordResetToken.objects.filter(
            is_used=True,
            used_at__lt=used_cutoff
        ).delete()[0]

        # ── Queue Logs — only SENT/FAILED, never touch PENDING ────────────────
        deleted_sms_logs = SMSQueue.objects.filter(
            status__in=[QueueStatus.SENT, QueueStatus.FAILED, QueueStatus.CANCELLED],
            created_at__lt=expired_cutoff
        ).delete()[0]

        deleted_mail_logs = MailQueue.objects.filter(
            status__in=[QueueStatus.SENT, QueueStatus.FAILED, QueueStatus.CANCELLED],
            created_at__lt=expired_cutoff
        ).delete()[0]

        # Mark cleanup as done in cache for next 5 minutes
        cache.set(CLEANUP_CACHE_KEY, True, CLEANUP_INTERVAL_SECONDS)

        self.stdout.write(self.style.SUCCESS(
            f"Database cleanup successfully completed:\n"
            f"- Expired Phone OTPs (unused >24h): {deleted_expired_otps}\n"
            f"- Expired Email Tokens (unused >24h): {deleted_expired_emails}\n"
            f"- Expired Password Reset Tokens (unused >24h): {deleted_expired_resets}\n"
            f"- Used Phone OTPs (cleared after 10m): {deleted_used_otps}\n"
            f"- Used Email Tokens (cleared after 10m): {deleted_used_emails}\n"
            f"- Used Password Reset Tokens (cleared after 10m): {deleted_used_resets}\n"
            f"- Completed SMS Logs (>24h): {deleted_sms_logs}\n"
            f"- Completed Mail Logs (>24h): {deleted_mail_logs}"
        ))

        self.stdout.write("--- Unified Cron Task Completed ---")