# apps/cauth/tasks.py
from celery import shared_task
from django.core.management import call_command


@shared_task(name='apps.cauth.tasks.process_sms_queue')
def process_sms_queue():
    """Delegates to the existing management command | zero logic duplication."""
    call_command('process_sms')  # your existing command name
    return "SMS queue processed"


@shared_task(name='apps.cauth.tasks.process_email_queue')
def process_email_queue():
    """Delegates to the existing management command | zero logic duplication."""
    call_command('process_email')  # your existing command name
    return "Email queue processed"