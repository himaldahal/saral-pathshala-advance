# auth/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
# from django_recaptcha.fields import ReCaptchaField  <-- UNCOMMENT FOR RECAPTCHA LATER
from .models import User, StudentLevel
from apps.pages.models import Course

class AestheticBaseForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control ui-input'
            visible.field.widget.attrs['placeholder'] = visible.field.label

class RegistrationForm(forms.ModelForm):
    # captcha = ReCaptchaField()  <-- UNCOMMENT FOR RECAPTCHA
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password_confirm = forms.CharField(widget=forms.PasswordInput, min_length=8)
    interested_course = forms.ModelChoiceField(queryset=Course.objects.all(), required=True, empty_label="Select a course")

    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone', 'previous_institute', 'current_level', 'interested_course']
        widgets = {
            'current_level': forms.Select(choices=StudentLevel.choices),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.visible_fields():
            base_class = 'form-select' if isinstance(visible.field.widget, forms.Select) else 'form-control'
            visible.field.widget.attrs['class'] = f'{base_class} ui-input'
            visible.field.widget.attrs['placeholder'] = visible.field.label

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('previous_institute'):
            raise ValidationError("Previous institute is required.")
        
        if not cleaned_data.get('current_level'):
            raise ValidationError("Current level is required.")
        
        if not cleaned_data.get('interested_course'):
            raise ValidationError("Interested course is required.")
        
        if not cleaned_data.get('phone'):
            raise ValidationError("Phone number is required.")
        
        if not cleaned_data.get('full_name'):
            raise ValidationError("Full name is required.")
        
        if not cleaned_data.get('email'):
            raise ValidationError("Email address is required.")

        pw1, pw2 = cleaned_data.get('password'), cleaned_data.get('password_confirm')
        if pw1 and pw2 and pw1 != pw2:
            raise ValidationError({'password_confirm': "Passwords do not match."})
        return cleaned_data

class LoginForm(AestheticBaseForm):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))
    
class OTPVerificationForm(AestheticBaseForm):
    otp = forms.CharField(max_length=6, min_length=6, widget=forms.TextInput(
        attrs={'autocomplete': 'one-time-code', 'type': 'number'}
    ))