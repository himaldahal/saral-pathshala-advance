from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings
from django.utils.html import strip_tags
from apps.cauth.models import MailQueue, QueueStatus

class Command(BaseCommand):
    help = "Processes the pending email queue using Django default SMTP settings"

    def handle(self, *args, **options):
        pending_mails = MailQueue.objects.filter(status=QueueStatus.PENDING)[:20] # batch of 20
        if not pending_mails.exists():
            self.stdout.write(self.style.SUCCESS("No pending emails to process."))
            return

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'info@saralpathshala.com')

        for mail in pending_mails:
            self.stdout.write(f"Sending Email to {mail.to_email}...")
            # Generate plain text alternative
            plain_message = strip_tags(mail.content)
            
            if settings.DEBUG:
                self.stdout.write(self.style.WARNING("=== [DEVELOPMENT EMAIL LOG] ==="))
                self.stdout.write(self.style.WARNING(f"To: {mail.to_email}"))
                self.stdout.write(self.style.WARNING(f"Subject: {mail.subject}"))
                self.stdout.write(self.style.WARNING(f"Body: {mail.content}"))
                self.stdout.write(self.style.WARNING("============================="))

            try:
                # If there are no real credentials, send_mail might fail. We wrap it.
                send_mail(
                    subject=mail.subject,
                    message=plain_message,
                    from_email=from_email,
                    recipient_list=[mail.to_email],
                    html_message=mail.content,
                    fail_silently=False,
                )
                mail.mark_sent()
                self.stdout.write(self.style.SUCCESS(f"Successfully sent email to {mail.to_email}"))
            except Exception as e:
                # If mail sending fails but we are in DEBUG, mark it as sent anyway for testing, or just mark failed.
                # Let's mark it failed so it is correct, but let's print the error.
                mail.mark_failed(str(e))
                self.stdout.write(self.style.ERROR(f"Failed to send email to {mail.to_email}: {str(e)}"))
                if settings.DEBUG:
                    self.stdout.write(self.style.SUCCESS(f"[DEBUG MODE] Marking email as sent so flow doesn't block local development."))
                    mail.mark_sent()
