# auth/utils.py
import code
import random
import string
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from apps.pages.models import Course
from .models import PhoneOTP, SMSQueue, MailQueue, User, EmailToken, PasswordResetToken

def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
    return ip

def enforce_otp_rate_limits(ip_address: str, phone: str) -> tuple[bool, str]:
    """Ensures 1 phone OTP per 10 minutes, and max 3 per hour. Also limits by IP address to prevent SMS abuse."""
    if not ip_address:
        ip_address = "unknown"
        
    # 1. IP-based limits (to prevent flooding SMS gateway by using multiple phone numbers)
    ip_ten_min_key = f"otp_limit_ip_10m_{ip_address}"
    ip_hourly_key = f"otp_limit_ip_hr_{ip_address}"
    
    ip_10m_attempts = cache.get(ip_ten_min_key, 0)
    if ip_10m_attempts >= 5:
        return False, "Too many OTP requests from your device. Please wait 10 minutes."
        
    ip_hr_attempts = cache.get(ip_hourly_key, 0)
    if ip_hr_attempts >= 10:
        return False, "Too many OTP requests from your device. Please try again in an hour."

    # 2. Phone-based limits
    ten_min_key = f"otp_phone_10m_{phone}"
    phone_hourly_key = f"otp_hr_limit_ph_{phone}"
    
    # 1 per 10 minute rule
    if cache.get(ten_min_key):
        return False, "Please wait 10 minutes before requesting another OTP."
    
    # 3 per hour rule for Phone
    phone_attempts = cache.get(phone_hourly_key, 0)
    if phone_attempts >= 3:
        return False, "Maximum hourly OTP requests reached for this phone number."
    
    # Set Cache Limits
    cache.set(ten_min_key, True, 600) # 10 minutes block
    cache.set(phone_hourly_key, phone_attempts + 1, 3600) # 1 hour limit
    cache.set(ip_ten_min_key, ip_10m_attempts + 1, 600) # 10 minutes block for IP
    cache.set(ip_hourly_key, ip_hr_attempts + 1, 3600) # 1 hour limit for IP
    return True, "Valid request"

def generate_and_dispatch_otp(user: User, request=None) -> tuple[bool, str]:
    """Generates 6-digit OTP, respects strict rate limits, valid for 24 hours, and enqueues SMS."""
    ip_address = get_client_ip(request) if request else ""
    phone = user.phone
    
    can_send, reason = enforce_otp_rate_limits(ip_address, phone)
    if not can_send:
        return False, reason
    
    # Invalidate prior pending OTPs for security
    PhoneOTP.objects.filter(user=user, is_used=False).update(is_used=True)
    
    # Generate 6 digit numeric code
    code = ''.join(random.choices(string.digits, k=6))
    
    # Save the DB entity (24 hours expiration as requested)
    expires_at = timezone.now() + timedelta(hours=24)
    PhoneOTP.objects.create(
        user=user,
        otp=code,
        ip_address=ip_address,
        expires_at=expires_at
    )
    
    # Push securely to SMS Queue
    message = f"{code} - Saral Pathshala OTP"
    SMSQueue.objects.create(user=user,to_phone=phone,message=message)
    
    trigger_queue_processing()
    return True, "OTP queued successfully"


def generate_and_dispatch_email_token(user: User, request=None) -> tuple[bool, str]:
    """Generates email verification token, respects 5 min rate limit, valid for 24 hours, and enqueues Mail."""
    email = user.email
    five_min_key = f"otp_email_5m_{email}"
    
    if cache.get(five_min_key):
        return False, "Please wait 5 minutes before requesting another email verification link."
        
    # IP-based rate limit
    ip_address = get_client_ip(request) if request else ""
    if ip_address:
        ip_key = f"otp_email_ip_hr_{ip_address}"
        ip_attempts = cache.get(ip_key, 0)
        if ip_attempts >= 5:
            return False, "Too many email verification requests from this device. Please try again in an hour."
        cache.set(ip_key, ip_attempts + 1, 3600)
        
    # Invalidate prior tokens
    EmailToken.objects.filter(user=user, is_used=False).update(is_used=True)
    
    expires_at = timezone.now() + timedelta(hours=24)
    email_token = EmailToken.objects.create(
        user=user,
        expires_at=expires_at
    )
    
    cache.set(five_min_key, True, 300) # 5 minutes block
    
    # Enqueue to MailQueue
    from django.urls import reverse
    if request:
        link = request.build_absolute_uri(reverse('verify_email', kwargs={'token': email_token.token}))
    else:
        link = f"/auth/verify-email/{email_token.token}/"
        
    subject = "Verify your Email - Saral Pathshala"
    content = f"""
    Hi {user.full_name},
    
    Thank you for registering at Saral Pathshala. Please verify your email by clicking the link below:
    
    {link}
    
    This link is valid for 24 hours.
    
    Regards,
    Saral Pathshala Team
    """

    MailQueue.objects.create(
        user=user,
        to_email=email,
        to_name=user.full_name,
        subject=subject,
        content=content
    )
    
    trigger_queue_processing()
    return True, "Verification email queued successfully"


def generate_and_dispatch_reset_token(user: User, request=None) -> tuple[bool, str]:
    """Generates password reset token, respects 5 min rate limit, valid for 24 hours, and enqueues Mail."""
    email = user.email
    five_min_key = f"otp_reset_5m_{email}"
    
    if cache.get(five_min_key):
        return False, "Please wait 5 minutes before requesting another reset link."
        
    # IP-based rate limit
    ip_address = get_client_ip(request) if request else ""
    if ip_address:
        ip_key = f"otp_reset_ip_hr_{ip_address}"
        ip_attempts = cache.get(ip_key, 0)
        if ip_attempts >= 5:
            return False, "Too many password reset requests from this device. Please try again in an hour."
        cache.set(ip_key, ip_attempts + 1, 3600)
        
    # Invalidate prior reset tokens
    PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)
    
    expires_at = timezone.now() + timedelta(hours=24) # 24 hours
    reset_token = PasswordResetToken.objects.create(
        user=user,
        expires_at=expires_at
    )
    
    cache.set(five_min_key, True, 300) # 5 minutes block
    
    # Enqueue to MailQueue
    from django.urls import reverse
    if request:
        link = request.build_absolute_uri(reverse('reset_password_confirm', kwargs={'token': reset_token.token}))
    else:
        link = f"/auth/reset-password/{reset_token.token}/"
        
    subject = "Reset your Password - Saral Pathshala"
    content = f"""
    Hi {user.full_name},
    
    We received a request to reset your password. You can reset your password by clicking the link below:
    
    {link}
    
    This link is valid for 24 hours.
    
    If you did not request a password reset, please ignore this email.
    
    Regards,
    Saral Pathshala Team
    """

    MailQueue.objects.create(
        user=user,
        to_email=email,
        to_name=user.full_name,
        subject=subject,
        content=content
    )
    
    trigger_queue_processing()
    return True, "Password reset email queued successfully"


def verify_recaptcha_token(token: str) -> bool:
    """Verifies Google reCAPTCHA v3 token against Google API."""
    import requests
    from django.conf import settings
    site_key = getattr(settings, 'RECAPTCHA_SITE_KEY', None)
    secret_key = getattr(settings, 'RECAPTCHA_SECRET_KEY', None)
    
    # Bypassed if site/secret keys are empty (for local developer convenience)
    if not site_key or not secret_key:
        return True
        
    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={
                'secret': secret_key,
                'response': token
            },
            timeout=5
        )
        res_data = response.json()
        # For reCAPTCHA v3, verify success and score >= 0.5
        return res_data.get('success', False) and res_data.get('score', 0.0) >= 0.5
    except Exception:
        # Fallback to true in case of request timeout to prevent blocking users on network failure
        return True

def trigger_queue_processing():
    """Spawns a background thread to process mail and SMS queues instantly."""
    import threading
    from django.core.management import call_command
    
    def run():
        try:
            call_command('process_mail_queue')
        except Exception as e:
            print(f"Background thread error processing mail queue: {e}")
        try:
            call_command('process_sms_queue')
        except Exception as e:
            print(f"Background thread error processing sms queue: {e}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()