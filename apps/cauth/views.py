# views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth import login, logout, authenticate
from django.urls import reverse
from django.db import transaction
from .models import User, PhoneOTP
from .forms import RegistrationForm, LoginForm, OTPVerificationForm
from .utils import get_client_ip, generate_and_dispatch_otp

def aesthetic_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data['email']
        password = form.cleaned_data['password']
        user = authenticate(request, email=email, password=password)
        
        if user is not None:
            # 1. Block access if phone is unverified, trigger OTP check flow
            if not user.is_phone_verified and not user.is_superuser:
                # Disptach a new code & stage their attempt securely
                generate_and_dispatch_otp(user, request)
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
            messages.error(request, "Invalid authentication credentials.")

    return render(request, 'login.html', {'form': form})

@transaction.atomic
def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
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
    user_id = request.session.get('auth_flow_user_id')
    if not user_id:
        messages.error(request, "Security token missing. Please login again.")
        return redirect('login')

    user = User.objects.get(id=user_id)
    
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

    return render(request, 'otp_verify.html', {'form': form, 'masked_phone': user.phone[-4:]})