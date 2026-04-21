from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Course
from apps.cauth.admin import ExportCsvMixin

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin, ExportCsvMixin):
    # What shows up in the main table
    list_display = ('display_thumbnail', 'name', 'is_active', 'tag_list', 'seo_score', 'created_at')
    list_filter = ('is_active', 'created_at', 'tags')
    search_fields = ('name', 'tags', 'description')
    list_editable = ('is_active',) # Quick toggle from the list view
    readonly_fields = ('display_thumbnail_large', 'slug', 'seo_excerpt', 'created_at')
    
    actions = ['export_as_csv', 'make_active', 'make_inactive']

    # Layout organization
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'is_active', ('thumbnail', 'display_thumbnail_large'))
        }),
        ('Content', {
            'fields': ('tags', 'description'),
            'classes': ('collapse',), # Hide by default to keep it clean
        }),
        ('SEO & Metadata', {
            'fields': ('seo_excerpt', 'created_at'),
            'description': 'SEO excerpt is auto-generated from description if left empty.'
        }),
    )

    # ── Custom View Methods ──────────────────────────────────────────────────

    def display_thumbnail(self, obj):
        """Small thumbnail for the list view"""
        if obj.thumbnail:
            return mark_safe(f'<img src="{obj.thumbnail.url}" width="50" height="50" style="border-radius: 4px; object-fit: cover;" />')
        return "No Image"
    display_thumbnail.short_description = "Preview"

    def display_thumbnail_large(self, obj):
        """Large preview for the detail view"""
        if obj.thumbnail:
            return mark_safe(f'<img src="{obj.thumbnail.url}" width="200" style="border-radius: 8px; border: 1px solid #ddd;" />')
        return "No Image uploaded"

    def tag_list(self, obj):
        """Render tags as pretty badges"""
        if not obj.tags:
            return "-"
        tags = obj.tags.split(',')
        tag_html = ''.join([f'<span class="badge" style="background:#e2e8f0; color:#475569; margin-right:3px;">{t.strip()}</span>' for t in tags])
        return mark_safe(tag_html)
    tag_list.short_description = "Tags"

    def seo_score(self, obj):
        """Visual SEO health check"""
        length = len(obj.seo_excerpt)
        if 120 <= length <= 160:
            color, label = "#059669", "Perfect"
        elif length > 0:
            color, label = "#d97706", "Needs Work"
        else:
            color, label = "#dc2626", "Missing"
        
        return mark_safe(f'<span style="color: {color}; font-weight: bold;">● {label}</span>')
    seo_score.short_description = "SEO"

    # ── Custom Actions ───────────────────────────────────────────────────────

    def make_active(self, request, queryset):
        queryset.update(is_active=True)
    make_active.short_description = "🟢 Mark as Active"

    def make_inactive(self, request, queryset):
        queryset.update(is_active=False)
    make_inactive.short_description = "🔴 Mark as Inactive"

    class Media:
        css = { 'all': ('admin/css/custom_admin.css',) }