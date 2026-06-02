from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth import login, logout, authenticate
from django.urls import reverse
from django.db import transaction
from django.core.cache import cache
from .models import User, PhoneOTP, PasswordResetToken, EmailToken
from .forms import RegistrationForm, LoginForm, OTPVerificationForm
from .utils import (
    get_client_ip, 
    generate_and_dispatch_otp, 
    generate_and_dispatch_reset_token, 
    generate_and_dispatch_email_token
)
from django.contrib.auth.decorators import login_required

def aesthetic_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    form = LoginForm(request.POST or None)
    if request.method == "POST":
        # Honeypot spam check
        if request.POST.get('website_url', '').strip():
            messages.success(request, "Secure login processed.")
            return redirect('login')
            
        # reCAPTCHA v3 Verification
        from .utils import verify_recaptcha_token
        recaptcha_token = request.POST.get('recaptcha_token', '').strip()
        if not verify_recaptcha_token(recaptcha_token):
            messages.error(request, "reCAPTCHA verification failed. Please try again.")
            return render(request, 'login.html', {'form': form})

        # Rate Limit Failed Login Attempts by IP and Email
        ip_address = get_client_ip(request)
        email = request.POST.get('email', '').strip().lower()
        
        login_attempts_ip_key = f"login_attempts_ip_{ip_address}"
        login_attempts_email_key = f"login_attempts_email_{email}"
        
        if cache.get(login_attempts_ip_key, 0) >= 10:
            messages.error(request, "Too many failed login attempts from your device. Please try again in 15 minutes.")
            return render(request, 'login.html', {'form': form})
            
        if email and cache.get(login_attempts_email_key, 0) >= 5:
            messages.error(request, "Too many failed login attempts for this account. Please try again in 15 minutes.")
            return render(request, 'login.html', {'form': form})

        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, email=email, password=password)
            
            if user is not None:
                # Clear rate limit counters on successful authentication
                cache.delete(login_attempts_ip_key)
                cache.delete(login_attempts_email_key)
                
                # 1. Block access if phone is unverified, trigger OTP check flow
                if not user.is_phone_verified and not user.is_superuser:
                    # Dispatch a new code & stage their attempt securely
                    success, msg = generate_and_dispatch_otp(user, request)
                    if not success:
                        # Even if the OTP send was rate-limited in the last 10 minutes,
                        # check if there is an existing valid pending OTP in the database.
                        active_otp = PhoneOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
                        if active_otp and not active_otp.is_expired:
                            request.session['auth_flow_user_id'] = str(user.id)
                            messages.warning(request, "An OTP was recently sent to your phone. Please enter it below to verify your account.")
                            return redirect('verify_otp')
                        else:
                            messages.error(request, f"OTP Blocked: {msg}")
                            return render(request, 'login.html', {'form': form})
                            
                    request.session['auth_flow_user_id'] = str(user.id)
                    messages.warning(request, "Device unfamiliar or phone not verified. OTP dispatched.")
                    return redirect('verify_otp')
                    
                # 2. Record clean access stats 
                user.last_login_ip = get_client_ip(request)
                user.last_login = timezone.now()
                user.save(update_fields=['last_login_ip', 'last_login'])
                login(request, user)
                return redirect('dashboard')
            else:
                # Increment failed login attempts
                ip_attempts = cache.get(login_attempts_ip_key, 0)
                cache.set(login_attempts_ip_key, ip_attempts + 1, 900) # 15 min lock
                
                if email:
                    email_attempts = cache.get(login_attempts_email_key, 0)
                    cache.set(login_attempts_email_key, email_attempts + 1, 900) # 15 min lock
                    
                messages.error(request, "Invalid authentication credentials.")

    return render(request, 'login.html', {'form': form})

@transaction.atomic
def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = RegistrationForm(request.POST or None)
    if request.method == "POST":
        # Honeypot spam check
        if request.POST.get('website_url', '').strip():
            messages.success(request, "Account secured. Please check your phone for the code.")
            return redirect('login')
            
        # reCAPTCHA v3 Verification
        from .utils import verify_recaptcha_token
        recaptcha_token = request.POST.get('recaptcha_token', '').strip()
        if not verify_recaptcha_token(recaptcha_token):
            messages.error(request, "reCAPTCHA verification failed. Please try again.")
            return render(request, 'register.html', {'form': form})

        if form.is_valid():
            # Cleanly instantiate
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()

            # Send first automated OTP. (Limits enforce logic but fresh users are unblocked).
            success, msg = generate_and_dispatch_otp(user, request)
            if not success:
                messages.error(request, f"User created, but OTP blocked: {msg}. You can log in to resend.")
            else:
                messages.success(request, "Account secured. Please check your phone for the code.")

            request.session['auth_flow_user_id'] = str(user.id)
            return redirect('verify_otp')

    return render(request, 'register.html', {'form': form})

def verify_otp(request):
    """Enforce OTP check independently via server session mapping without direct DB query parameter exploits."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    user_id = request.session.get('auth_flow_user_id')
    if not user_id:
        messages.error(request, "Security token missing. Please login again.")
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        if 'auth_flow_user_id' in request.session:
            del request.session['auth_flow_user_id']
        messages.error(request, "User account not found. Please register or login again.")
        return redirect('login')
    
    # Handle optional automatic resend button hit via GET param/forms
    if request.method == "POST" and "resend_action" in request.POST:
        success, msg = generate_and_dispatch_otp(user, request)
        if success:
            messages.success(request, "New OTP has been dispatched.")
        else:
            messages.error(request, msg)
        return redirect('verify_otp')

    form = OTPVerificationForm(request.POST or None)
    if request.method == "POST" and "resend_action" not in request.POST and form.is_valid():
        code = form.cleaned_data['otp']
        # Locate the user's latest active OTP record
        active_otp = PhoneOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()
        
        if not active_otp:
            messages.error(request, "No pending OTP. Please request a resend.")
        else:
            valid, outcome_message = active_otp.verify(code)
            if valid:
                user.is_phone_verified = True
                user.save(update_fields=['is_phone_verified'])
                
                # Cleanup and establish proper login session
                del request.session['auth_flow_user_id']
                login(request, user)
                
                # Optional email queue could theoretically run here to verify their initial welcome
                messages.success(request, outcome_message)
                return redirect('dashboard')
            else:
                messages.error(request, outcome_message)

    return render(request, 'otp_verify.html', {'form': form, 'masked_phone': user.phone[-4:] if user.phone else "XXXX"})

@login_required
def u_logout(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')

def forgot_password(request):
    """Enables users to request a password reset link sent to their email."""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == "POST":
        # Honeypot spam check
        if request.POST.get('website_url', '').strip():
            messages.success(request, "If that email exists in our records, a reset link has been dispatched.")
            return redirect('login')
            
        email = request.POST.get('email', '').strip()
        user = User.objects.filter(email=email).first()
        if user:
            success, msg = generate_and_dispatch_reset_token(user, request)
            if success:
                messages.success(request, "A password reset link has been dispatched to your email address.")
                return redirect('login')
            else:
                messages.error(request, msg)
        else:
            messages.success(request, "If that email exists in our records, a reset link has been dispatched.")
            return redirect('login')
            
    return render(request, 'forgot_password.html')

def reset_password_confirm(request, token):
    """Verifies the reset token and lets the user update their password."""
    reset_token = get_object_or_404(PasswordResetToken, token=token)
    if not reset_token.is_valid:
        messages.error(request, "This password reset token has expired or already been used.")
        return redirect('login')
        
    if request.method == "POST":
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        
        if not password or len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
        elif password != password_confirm:
            messages.error(request, "Passwords do not match.")
        else:
            reset_token.consume(password)
            messages.success(request, "Your password has been reset successfully. You can now log in.")
            return redirect('login')
            
    return render(request, 'reset_password_confirm.html', {'token': token})

def verify_email(request, token):
    """Verifies student email when clicking the emailed link."""
    email_token = get_object_or_404(EmailToken, token=token)
    if not email_token.is_valid:
        messages.error(request, "Verification link has expired or already been used.")
        return redirect('login')
        
    email_token.consume()
    messages.success(request, "Your email address has been verified successfully!")
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')

def auth_home(request):
    """
    Redirect /auth/ directly to /auth/login/
    """
    return redirect('login')