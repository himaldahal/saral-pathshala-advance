"""
Saral Pathshala – Auth Forms
-----------------------------
RegisterForm, LoginForm, OTPVerifyForm,
ForgotPasswordForm, ResetPasswordForm.

Google reCAPTCHA integration:
  1. pip install django-recaptcha
  2. Add 'django_recaptcha' to INSTALLED_APPS
  3. Set RECAPTCHA_PUBLIC_KEY / RECAPTCHA_PRIVATE_KEY in settings
  4. Uncomment the captcha field in each form below  ← marked with # RECAPTCHA
"""

from django import forms
from django.core.validators import RegexValidator

from .models import User, StudentLevel

try:
    from apps.pages.models import Course
    COURSE_CHOICES_AVAILABLE = True
except ImportError:
    COURSE_CHOICES_AVAILABLE = False

# ── Uncomment to enable reCAPTCHA ────────────────────────────────────────────
# from django_recaptcha.fields import ReCaptchaField
# from django_recaptcha.widgets import ReCaptchaV2Checkbox

nepal_phone_validator = RegexValidator(
    regex=r'^(97|98)\d{8}$',
    message="Enter a valid Nepali mobile number (e.g. 9841234567).",
)

PASSWORD_MIN_LENGTH = 8


# ── Register Form ─────────────────────────────────────────────────────────────
class RegisterForm(forms.ModelForm):
    password  = forms.CharField(
        label="Password",
        min_length=PASSWORD_MIN_LENGTH,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'id': 'id_password',
            'placeholder': 'Create a strong password',
            'autocomplete': 'new-password',
        }),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'id': 'id_password2',
            'placeholder': 'Repeat your password',
            'autocomplete': 'new-password',
        }),
    )

    # RECAPTCHA: Uncomment the line below to enable reCAPTCHA on registration
    # captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())

    class Meta:
        model  = User
        fields = [
            'full_name', 'email', 'phone',
            'current_level', 'previous_institute', 'interested_course',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your full name',
                'autocomplete': 'name',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com',
                'autocomplete': 'email',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '98XXXXXXXX',
                'maxlength': '10',
                'autocomplete': 'tel',
                'inputmode': 'numeric',
            }),
            'current_level': forms.Select(attrs={
                'class': 'form-select',
            }),
            'previous_institute': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. ABC Secondary School',
            }),
            'interested_course': forms.Select(attrs={
                'class': 'form-select',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make non-critical fields optional
        self.fields['previous_institute'].required = False
        self.fields['current_level'].required      = False
        self.fields['interested_course'].required  = False

        # Add empty label to select fields
        self.fields['current_level'].empty_label = '— Select your level —'   # type: ignore[attr-defined]
        if COURSE_CHOICES_AVAILABLE:
            self.fields['interested_course'].queryset = Course.objects.filter(is_active=True)
            self.fields['interested_course'].empty_label = '— Choose a course (optional) —'

        # Required field visual cue
        for name in ('full_name', 'email', 'phone', 'password', 'password2'):
            self.fields[name].required = True

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("This phone number is already registered.")
        return phone

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        if len(password) < PASSWORD_MIN_LENGTH:
            raise forms.ValidationError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


# ── Login Form ────────────────────────────────────────────────────────────────
class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your password',
            'autocomplete': 'current-password',
            'id': 'id_login_password',
        }),
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Keep me signed in",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    # RECAPTCHA: Uncomment to add reCAPTCHA on login
    # captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())

    def clean_email(self):
        return self.cleaned_data['email'].lower().strip()


# ── OTP Verify Form ───────────────────────────────────────────────────────────
class OTPVerifyForm(forms.Form):
    otp = forms.CharField(
        label="Enter OTP",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control otp-input',
            'placeholder': '——————',
            'maxlength': '6',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'autofocus': True,
        }),
    )

    def clean_otp(self):
        otp = self.cleaned_data.get('otp', '').strip()
        if not otp.isdigit():
            raise forms.ValidationError("OTP must be 6 digits.")
        return otp


# ── Forgot Password Form ──────────────────────────────────────────────────────
class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        label="Registered Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
            'autofocus': True,
        }),
    )

    # RECAPTCHA: Uncomment to protect password reset with reCAPTCHA
    # captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox())

    def clean_email(self):
        return self.cleaned_data['email'].lower().strip()


# ── Reset Password Form ───────────────────────────────────────────────────────
class ResetPasswordForm(forms.Form):
    password  = forms.CharField(
        label="New Password",
        min_length=PASSWORD_MIN_LENGTH,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a new password',
            'id': 'id_new_password',
            'autocomplete': 'new-password',
        }),
    )
    password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Repeat new password',
            'id': 'id_new_password2',
            'autocomplete': 'new-password',
        }),
    )

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        if len(password) < PASSWORD_MIN_LENGTH:
            raise forms.ValidationError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Passwords do not match.")
        return cleaned