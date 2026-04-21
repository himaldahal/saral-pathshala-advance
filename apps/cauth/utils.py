"""
Saral Pathshala – Auth Utilities
---------------------------------
OTP generation, rate-limiting (cache-based, no Redis),
IP extraction, and queue helpers.
"""

import random
import string
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from .models import (
    EmailToken, MailQueue, PasswordResetToken,
    PhoneOTP, SMSQueue,
    OTP_EXPIRY_MINUTES, EMAIL_TOKEN_EXPIRY_HOURS, RESET_TOKEN_EXPIRY_MINUTES,
)

# ── Rate Limit Constants ──────────────────────────────────────────────────────
OTP_COOLDOWN_SECONDS = 300   # 5 minutes between OTPs
OTP_HOURLY_LIMIT     = 3     # max 3 OTPs per hour per phone/IP


# ── IP Extraction ─────────────────────────────────────────────────────────────
def get_client_ip(request) -> str:
    """Return the real client IP, honouring reverse-proxy headers."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


# ── Phone Masking ─────────────────────────────────────────────────────────────
def mask_phone(phone: str) -> str:
    """e.g. '9841234567' → '98****4567'"""
    if not phone or len(phone) < 6:
        return phone
    return phone[:2] + '*' * (len(phone) - 6) + phone[-4:]


# ── OTP Generation ────────────────────────────────────────────────────────────
def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))


# ── Cache-Key Helpers ─────────────────────────────────────────────────────────
def _cooldown_key(kind: str, value: str) -> str:
    return f'otp:cooldown:{kind}:{value}'


def _hourly_key(kind: str, value: str) -> str:
    return f'otp:hourly:{kind}:{value}'


# ── Rate Limit Check ──────────────────────────────────────────────────────────
def check_otp_rate_limit(phone: str = None, ip: str = None) -> tuple[bool, str]:
    """
    Returns (allowed, error_message).
    Checks both phone and IP:
      - 1 OTP per 5 minutes
      - 3 OTPs per hour
    """
    checks = []
    if phone:
        checks.append(('phone', phone))
    if ip:
        checks.append(('ip', ip))

    for kind, value in checks:
        if cache.get(_cooldown_key(kind, value)):
            wait = "5 minutes" if kind == 'phone' else "5 minutes"
            return False, f"Please wait {wait} before requesting another OTP."
        hourly = cache.get(_hourly_key(kind, value), 0)
        if hourly >= OTP_HOURLY_LIMIT:
            target = "your phone number" if kind == 'phone' else "your network"
            return False, f"Too many OTP requests for {target}. Try again in an hour."

    return True, ""


def record_otp_sent(phone: str = None, ip: str = None):
    """Record an OTP send event in cache for rate limiting."""
    for kind, value in [('phone', phone), ('ip', ip)]:
        if not value:
            continue
        cache.set(_cooldown_key(kind, value), 1, OTP_COOLDOWN_SECONDS)
        hourly = cache.get(_hourly_key(kind, value), 0)
        cache.set(_hourly_key(kind, value), hourly + 1, 3600)


def get_otp_cooldown_remaining(phone: str = None, ip: str = None) -> int:
    """Returns seconds remaining on cooldown (0 if none)."""
    for kind, value in [('phone', phone), ('ip', ip)]:
        if not value:
            continue
        ttl = cache.ttl(_cooldown_key(kind, value))
        if ttl and ttl > 0:
            return ttl
    return 0


# ── OTP Create & Queue ────────────────────────────────────────────────────────
def create_and_queue_phone_otp(user, ip: str) -> PhoneOTP:
    """
    Invalidate old OTPs, create a fresh one, push to SMSQueue.
    Call record_otp_sent() AFTER this if you want rate limiting.
    """
    # Invalidate any previous unused OTPs for this user
    PhoneOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    otp_code = generate_otp()
    phone_otp = PhoneOTP.objects.create(
        user=user,
        otp=otp_code,
        ip_address=ip,
        expires_at=timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
    )

    SMSQueue.objects.create(
        user=user,
        to_phone=user.phone,
        message=(
            f"Your Saral Pathshala OTP is {otp_code}. "
            f"Valid for {OTP_EXPIRY_MINUTES} minutes. Do not share."
        ),
    )
    return phone_otp


def get_latest_valid_otp(user) -> PhoneOTP | None:
    """Return the most recent unused, unexpired OTP for a user."""
    return (
        PhoneOTP.objects
        .filter(user=user, is_used=False, expires_at__gt=timezone.now())
        .order_by('-created_at')
        .first()
    )


# ── Email Token Helpers ───────────────────────────────────────────────────────
def create_and_queue_email_token(user, request) -> EmailToken:
    """Create an email verification token and queue the email."""
    # Invalidate previous tokens
    EmailToken.objects.filter(user=user, is_used=False).update(is_used=True)

    token = EmailToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=EMAIL_TOKEN_EXPIRY_HOURS),
    )

    verify_url = request.build_absolute_uri(f'/accounts/email-verify/{token.token}/')

    html_body = f"""
    <p>Hi {user.get_short_name()},</p>
    <p>Click the button below to verify your email address for Saral Pathshala.</p>
    <p>
      <a href="{verify_url}" style="
         background:#2D89C8;color:#fff;padding:12px 24px;
         border-radius:6px;text-decoration:none;display:inline-block;">
        Verify Email
      </a>
    </p>
    <p>This link expires in {EMAIL_TOKEN_EXPIRY_HOURS} hours.</p>
    <p>If you didn't request this, ignore this email.</p>
    """

    MailQueue.objects.create(
        user=user,
        to_email=user.email,
        to_name=user.get_short_name(),
        subject="Verify your email – Saral Pathshala",
        content=html_body,
    )
    return token


# ── Password Reset Helpers ────────────────────────────────────────────────────
def create_and_queue_reset_token(user, request) -> PasswordResetToken:
    """Create a password reset token and queue the email."""
    PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)

    token = PasswordResetToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES),
    )

    reset_url = request.build_absolute_uri(f'/accounts/reset-password/{token.token}/')

    html_body = f"""
    <p>Hi {user.get_short_name()},</p>
    <p>We received a request to reset your Saral Pathshala password.</p>
    <p>
      <a href="{reset_url}" style="
         background:#2D89C8;color:#fff;padding:12px 24px;
         border-radius:6px;text-decoration:none;display:inline-block;">
        Reset Password
      </a>
    </p>
    <p>This link expires in {RESET_TOKEN_EXPIRY_MINUTES} minutes.</p>
    <p>If you didn't request this, ignore this email — your password won't change.</p>
    """

    MailQueue.objects.create(
        user=user,
        to_email=user.email,
        to_name=user.get_short_name(),
        subject="Reset your password – Saral Pathshala",
        content=html_body,
    )
    return token