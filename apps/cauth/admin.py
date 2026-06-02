import csv
from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.db.models import Count, Q
from django.utils import timezone
from .models import (
    User, MailQueue, SMSQueue, PhoneOTP, 
    EmailToken, PasswordResetToken, QueueStatus
)

# ── Base Admin for Exports ──────────────────────────────────────────────────
class ExportCsvMixin:
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={meta}.csv'
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])
        return response
    export_as_csv.short_description = "🚀 Export Selected to CSV"


# ── Custom Filters ──────────────────────────────────────────────────────────
class VerificationFilter(admin.SimpleListFilter):
    title = 'Verification Status'
    parameter_name = 'verified'

    def lookups(self, request, model_admin):
        return (
            ('both', 'Fully Verified'),
            ('phone', 'Phone Only'),
            ('email', 'Email Only'),
            ('none', 'Unverified'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'both':
            return queryset.filter(is_phone_verified=True, is_email_verified=True)
        if self.value() == 'phone':
            return queryset.filter(is_phone_verified=True, is_email_verified=False)
        if self.value() == 'none':
            return queryset.filter(is_phone_verified=False, is_email_verified=False)
        return queryset


# ── User Admin ──────────────────────────────────────────────────────────────
@admin.register(User)
class UserAdmin(admin.ModelAdmin, ExportCsvMixin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    list_display = ('full_name', 'email', 'phone', 'level_badge', 'verify_status', 'date_joined', 'is_staff')
    list_filter = (VerificationFilter, 'current_level', 'is_staff', 'date_joined')
    search_fields = ('full_name', 'email', 'phone')
    ordering = ('-date_joined',)
    actions = ['export_as_csv', 'mark_verified']
    
    readonly_fields = ('id', 'date_joined', 'updated_at', 'last_login_ip')
    
    fieldsets = (
        ('Personal Info', {'fields': ('id', 'full_name', 'email', 'phone', 'password')}),
        ('Academic Info', {'fields': ('current_level', 'interested_course', 'previous_institute')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_phone_verified', 'is_email_verified')}),
        ('Metadata', {'fields': ('date_joined', 'last_login', 'last_login_ip')}),
    )

    def level_badge(self, obj):
        colors = {'plus_two': '#6366f1', 'bachelors': '#8b5cf6', 'masters': '#ec4899'}
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 10px;">{}</span>',
            colors.get(obj.current_level, '#64748b'),
            obj.get_current_level_display()
        )
    level_badge.short_description = "Level"

    def verify_status(self, obj):
        p_color = "green" if obj.is_phone_verified else "red"
        e_color = "green" if obj.is_email_verified else "red"
        return format_html(
            '<b style="color:{};">P</b> | <b style="color:{};">E</b>', 
            p_color, e_color
        )
    verify_status.short_description = "P|E"

    def mark_verified(self, request, queryset):
        queryset.update(is_phone_verified=True, is_email_verified=True)
    mark_verified.short_description = "✅ Mark selected as Fully Verified"

    class Media:
        css = { 'all': ('admin/css/custom_admin.css',) }


# ── Queue Admin (Mail & SMS) ────────────────────────────────────────────────
class BaseQueueAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = ('id', 'target', 'status_badge', 'retry_count', 'created_at')
    list_filter = ('status', 'created_at')
    actions = ['export_as_csv', 'retry_failed_tasks']

    def status_badge(self, obj):
        css_class = f"badge-{obj.status}"
        return format_html('<span class="badge {}">{}</span>', css_class, obj.status)
    status_badge.short_description = "Status"

    def retry_failed_tasks(self, request, queryset):
        queryset.update(status=QueueStatus.PENDING, retry_count=0)
    retry_failed_tasks.short_description = "🔄 Reset & Retry Tasks"

@admin.register(MailQueue)
class MailQueueAdmin(BaseQueueAdmin):
    list_display = ('to_email', 'subject', 'status_badge', 'retry_count', 'sent_at')
    search_fields = ('to_email', 'subject')
    def target(self, obj): return obj.to_email

@admin.register(SMSQueue)
class SMSQueueAdmin(BaseQueueAdmin):
    list_display = ('to_phone', 'message_preview', 'status_badge', 'retry_count', 'sent_at')
    search_fields = ('to_phone', 'message')
    def target(self, obj): return obj.to_phone
    def message_preview(self, obj): return obj.message[:30] + "..."


# ── Security Admin (OTPs & Tokens) ──────────────────────────────────────────
@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp', 'is_used', 'attempts', 'is_expired_status', 'created_at')
    list_filter = ('is_used', 'created_at')
    readonly_fields = ('otp', 'created_at', 'expires_at')

    def is_expired_status(self, obj):
        return obj.is_expired
    is_expired_status.boolean = True
    is_expired_status.short_description = "Expired?"

@admin.register(PasswordResetToken)
class PasswordResetAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'is_used', 'expires_at')
    search_fields = ('user__email',)

admin.site.register(EmailToken)

# ── Site Customization ──────────────────────────────────────────────────────
admin.site.site_header = "🎓 Saral Pathshala — Command Center"
admin.site.site_title = "Saral Pathshala Command Center"
admin.site.index_title = "Platform Administration & Systems Control"