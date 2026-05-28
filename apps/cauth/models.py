"""
Saral Pathshala – Authentication & Queue Models
------------------------------------------------
Includes: Custom User, MailQueue, SMSQueue,
          PhoneOTP, EmailToken, PasswordResetToken
"""

import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from apps.pages.models import Course

# ── Validators ───────────────────────────────────────────────────────────────
nepal_phone_validator = RegexValidator(
    regex=r'^(97|98)\d{8}$',
    message="Phone must be 10 digits starting with 97 or 98 (e.g. 9841234567).",
)

MAX_ATTEMPTS = 3
OTP_MAX_VERIFY_ATTEMPTS = 5
OTP_EXPIRY_MINUTES = 10
EMAIL_TOKEN_EXPIRY_HOURS = 24
RESET_TOKEN_EXPIRY_MINUTES = 30


# ── User Manager ─────────────────────────────────────────────────────────────
class UserManager(BaseUserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_phone_verified', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


# ── User ─────────────────────────────────────────────────────────────────────
class StudentLevel(models.TextChoices):
    PLUS_TWO  = 'plus_two',  '+2 (Grade XI/XII)'
    BACHELORS = 'bachelors', 'Bachelors'
    MASTERS   = 'masters',   'Masters'


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    full_name = models.CharField(max_length=60)
    email     = models.EmailField(unique=True, db_index=True)
    phone     = models.CharField(max_length=10, unique=True, null=True, blank=True,validators=[nepal_phone_validator], db_index=True,)
    previous_institute = models.CharField(max_length=200, blank=True)
    current_level      = models.CharField(max_length=20, choices=StudentLevel.choices, blank=True, null=True)
    interested_course  = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True,related_name='interested_students',to_field='slug')

    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_active         = models.BooleanField(default=True)
    is_staff          = models.BooleanField(default=False)

    date_joined   = models.DateTimeField(default=timezone.now)
    last_login    = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.CharField(max_length=200, blank=True, null=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name        = "User"
        verbose_name_plural = "Users"
        ordering            = ['-date_joined']

    def __str__(self):
        return self.email

    def can_login(self):
        if self.is_staff or self.is_superuser:
            return True
        return self.is_phone_verified

    def get_full_name(self):
        return self.full_name or self.email

    def get_short_name(self):
        name = self.get_full_name()
        return name.split()[0] if name else self.email


# ── Queue Status ─────────────────────────────────────────────────────────────
class QueueStatus(models.TextChoices):
    PENDING   = 'pending',   'Pending'
    SENT      = 'sent',      'Sent'
    FAILED    = 'failed',    'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


# ── Mail Queue ────────────────────────────────────────────────────────────────
class MailQueue(models.Model):
    """Processed by: python manage.py process_mail_queue"""

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='mail_queue')
    to_email = models.EmailField()
    to_name  = models.CharField(max_length=120, blank=True)

    subject  = models.CharField(max_length=250)
    content  = models.TextField(blank=True, help_text="HTML email body.")

    retry_count    = models.PositiveSmallIntegerField(default=0)
    status         = models.CharField(max_length=15, choices=QueueStatus.choices, default=QueueStatus.PENDING, db_index=True)
    failure_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "Mail Queue"
        verbose_name_plural = "Mail Queue"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['to_email']),
        ]

    def __str__(self):
        return f"[{self.status.upper()}] {self.subject} → {self.to_email}"

    def mark_sent(self):
        self.status  = QueueStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at'])

    def mark_failed(self, reason: str = ''):
        self.retry_count += 1
        self.status = QueueStatus.FAILED if self.retry_count >= MAX_ATTEMPTS else QueueStatus.PENDING
        self.failure_reason = reason
        self.save(update_fields=['status', 'retry_count', 'failure_reason'])


# ── SMS Queue ─────────────────────────────────────────────────────────────────
class SMSQueue(models.Model):
    """Processed by: python manage.py process_sms_queue, all the used, send or unsent otps are auto removed in every 24 hours """

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sms_queue')
    to_phone = models.CharField(max_length=10, validators=[nepal_phone_validator])

    message     = models.CharField(max_length=160)
    retry_count = models.PositiveSmallIntegerField(default=0)

    status         = models.CharField(max_length=15, choices=QueueStatus.choices, default=QueueStatus.PENDING, db_index=True)
    failure_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at    = models.DateTimeField(null=True, blank=True)   # ← was missing in original

    class Meta:
        verbose_name        = "SMS Queue"
        verbose_name_plural = "SMS Queue"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['to_phone']),
        ]

    def __str__(self):
        return f"[{self.status.upper()}] SMS → {self.to_phone}"

    def mark_sent(self):
        self.status  = QueueStatus.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at'])

    def mark_failed(self, reason: str = ''):
        self.retry_count += 1
        self.status = QueueStatus.FAILED if self.retry_count >= MAX_ATTEMPTS else QueueStatus.PENDING
        self.failure_reason = reason
        self.save(update_fields=['status', 'retry_count', 'failure_reason'])


# NEW: OTP & Token Models 
class PhoneOTP(models.Model):
    """
    One-time password for phone verification.
    Created during registration or when a verified user needs re-auth.
    Invalidated after use or expiry.
    
    all the OTPS older than 1 hour are automatically deleted every 24 hours.
    """
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='phone_otps')
    otp        = models.CharField(max_length=6)
    ip_address = models.CharField(max_length=45, blank=True)

    is_used  = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name        = "Phone OTP"
        verbose_name_plural = "Phone OTPs"
        ordering            = ['-created_at']
        indexes             = [models.Index(fields=['user', 'is_used'])]

    def __str__(self):
        return f"OTP for {self.user.phone} ({'used' if self.is_used else 'pending'})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired and self.attempts < OTP_MAX_VERIFY_ATTEMPTS

    def verify(self, entered_otp: str) -> tuple[bool, str]:
        """
        Returns (success: bool, message: str).
        Increments attempt counter on each wrong try.
        """
        if self.attempts >= OTP_MAX_VERIFY_ATTEMPTS:
            return False, "Too many incorrect attempts. Request a new OTP."
        if self.is_expired:
            return False, "OTP has expired. Please request a new one."
        if self.is_used:
            return False, "This OTP has already been used."

        self.attempts += 1
        if self.otp != entered_otp.strip():
            self.save(update_fields=['attempts'])
            remaining = OTP_MAX_VERIFY_ATTEMPTS - self.attempts
            return False, f"Incorrect OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining."

        self.is_used = True
        self.save(update_fields=['is_used', 'attempts'])
        return True, "Phone number verified successfully."


class EmailToken(models.Model):
    """Token sent via email to verify the user's email address (optional flow). used or unused all of them are flushed deleted every 24 hours too"""

    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_tokens')
    token    = models.UUIDField(default=uuid.uuid4, unique=True)
    is_used  = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name        = "Email Verification Token"
        verbose_name_plural = "Email Verification Tokens"
        ordering            = ['-created_at']

    def __str__(self):
        return f"EmailToken({self.user.email}, used={self.is_used})"

    @property
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def consume(self):
        self.is_used = True
        self.save(update_fields=['is_used'])
        self.user.is_email_verified = True
        self.user.save(update_fields=['is_email_verified'])


class PasswordResetToken(models.Model):
    """Short-lived token for password reset (30 min window).
    
    and all of the unsued older tokens are deleted in every 24 hours automatically."""
    
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token    = models.UUIDField(default=uuid.uuid4, unique=True)
    is_used  = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name        = "Password Reset Token"
        verbose_name_plural = "Password Reset Tokens"
        ordering            = ['-created_at']

    def __str__(self):
        return f"ResetToken({self.user.email}, used={self.is_used})"

    @property
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def consume(self, new_password: str):
        self.is_used = True
        self.save(update_fields=['is_used'])
        self.user.set_password(new_password)
        self.user.save(update_fields=['password'])