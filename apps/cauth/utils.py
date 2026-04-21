# auth/utils.py
import random
import string
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from apps.pages.models import Course # Based on your prompt structure
from .models import PhoneOTP, SMSQueue, MailQueue, User

def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
    return ip

def enforce_otp_rate_limits(ip_address: str, phone: str) -> tuple[bool, str]:
    """Ensures 1 OTP per 5 min, max 3 per hour via IP and Phone limits."""
    five_min_key = f"otp_5m_limit_{phone}"
    ip_hourly_key = f"otp_hr_limit_{ip_address}"
    phone_hourly_key = f"otp_hr_limit_ph_{phone}"
    
    # 1 per 5 minute rule
    if cache.get(five_min_key):
        return False, "Please wait 5 minutes before requesting another OTP."
    
    # 3 per hour rule for IP
    ip_attempts = cache.get(ip_hourly_key, 0)
    if ip_attempts >= 3:
        return False, "Maximum hourly OTP requests reached for your IP address."
        
    # 3 per hour rule for Phone
    phone_attempts = cache.get(phone_hourly_key, 0)
    if phone_attempts >= 3:
        return False, "Maximum hourly OTP requests reached for this phone number."
    
    # Increment or Set Cache Limits
    cache.set(five_min_key, True, 300) # 5 minutes block
    cache.set(ip_hourly_key, ip_attempts + 1, 3600) # 1 hr cache
    cache.set(phone_hourly_key, phone_attempts + 1, 3600)
    return True, "Valid request"

def generate_and_dispatch_otp(user: User, request=None) -> tuple[bool, str]:
    """Generates 6-digit OTP, respects strict rules, saves OTP, and enqueues SMS."""
    ip_address = get_client_ip(request) if request else ""
    phone = user.phone
    
    can_send, reason = enforce_otp_rate_limits(ip_address, phone)
    if not can_send:
        return False, reason
    
    # Invalidate prior pending OTPs for security
    PhoneOTP.objects.filter(user=user, is_used=False).update(is_used=True)
    
    # Generate 6 digit numeric code
    code = ''.join(random.choices(string.digits, k=6))
    
    # Save the DB entity (10-min expiration as requested in your base logic)
    expires_at = timezone.now() + timedelta(minutes=10)
    PhoneOTP.objects.create(
        user=user,
        otp=code,
        ip_address=ip_address,
        expires_at=expires_at
    )
    
    # Push securely to SMS Queue
    message = f"{code} is your verification code for Saral Pathshala. Do not share this with anyone."
    SMSQueue.objects.create(
        user=user,
        to_phone=phone,
        message=message
    )
    
    return True, "OTP queued successfully"