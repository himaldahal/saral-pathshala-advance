from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count

from .models import (
    Course,
    Subject,
    Section,
    Lecture,
    Enrollment,
    LectureProgress
)


# ─────────────────────────────────────────────
# CUSTOM ADMIN BRANDING
# ─────────────────────────────────────────────
admin.site.site_header = "🎓 EduPanel — Course Manager"
admin.site.site_title = "EduPanel Admin"
admin.site.index_title = "Content Management"


# ─────────────────────────────────────────────
# SHARED ADMIN STYLES
# ─────────────────────────────────────────────
ADMIN_EXTRA_STYLES = """
<style>
    .drag-handle{
        cursor:grab;
        color:#9aa0a6;
        font-size:18px;
        user-select:none;
    }

    .drag-handle:hover{
        color:#202124;
    }

    .sortable-rows tr:hover{
        background:#f8f9fa;
    }

    .order-badge{
        display:inline-flex;
        align-items:center;
        justify-content:center;
        width:26px;
        height:26px;
        border-radius:50%;
        background:#1a73e8;
        color:#fff;
        font-size:11px;
        font-weight:700;
    }

    .course-chip{
        display:inline-flex;
        align-items:center;
        padding:3px 10px;
        border-radius:999px;
        background:#e8f0fe;
        color:#1a73e8;
        font-size:11px;
        font-weight:600;
        margin:2px;
    }

    .admin-thumb{
        border-radius:6px;
        border:1px solid #ddd;
        object-fit:cover;
    }

    .video-frame{
        position:relative;
        width:100%;
        max-width:500px;
        padding-top:56.25%;
        border-radius:10px;
        overflow:hidden;
        background:#000;
    }

    .video-frame iframe{
        position:absolute;
        top:0;
        left:0;
        width:100%;
        height:100%;
    }

    .progress-wrap{
        width:140px;
        background:#ececec;
        border-radius:999px;
        overflow:hidden;
        height:10px;
        margin-bottom:4px;
    }

    .progress-bar{
        height:10px;
        border-radius:999px;
    }

    .inline-group .tabular td{
        vertical-align:middle;
    }
</style>
"""


# ─────────────────────────────────────────────
# BASE ADMIN MIXIN
# ─────────────────────────────────────────────
class AdminStyleMixin:
    """
    Inject shared CSS into admin pages.
    """

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["extra_admin_style"] = mark_safe(ADMIN_EXTRA_STYLES)
        return super().changelist_view(request, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["extra_admin_style"] = mark_safe(ADMIN_EXTRA_STYLES)
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["extra_admin_style"] = mark_safe(ADMIN_EXTRA_STYLES)
        return super().add_view(request, form_url, extra_context)


# ─────────────────────────────────────────────
# INLINE: LECTURE INSIDE SECTION
# ─────────────────────────────────────────────
class LectureInline(admin.TabularInline):
    model = Lecture
    extra = 0

    fields = (
        'drag_order',
        'order',
        'title',
        'youtube_embed_url',
        'duration',
        'is_preview',
    )

    readonly_fields = ('drag_order',)

    ordering = ('order', 'id')

    show_change_link = True

    classes = ('sortable-rows',)

    def drag_order(self, obj):
        return mark_safe(
            '<span class="drag-handle" title="Drag to reorder">⠿</span>'
        )

    drag_order.short_description = ''


# ─────────────────────────────────────────────
# INLINE: SECTION INSIDE SUBJECT
# ─────────────────────────────────────────────
class SectionInline(admin.TabularInline):
    model = Section
    extra = 0

    fields = (
        'drag_order',
        'order',
        'title',
    )

    readonly_fields = ('drag_order',)

    ordering = ('order', 'id')

    show_change_link = True

    classes = ('sortable-rows',)

    def drag_order(self, obj):
        return mark_safe(
            '<span class="drag-handle" title="Drag to reorder">⠿</span>'
        )

    drag_order.short_description = ''


# ─────────────────────────────────────────────
# SUBJECT ADMIN
# ─────────────────────────────────────────────
@admin.register(Subject)
class SubjectAdmin(AdminStyleMixin, admin.ModelAdmin):

    list_display = (
        'order_badge',
        'name',
        'courses_list',
        'lecture_count',
        'is_active',
        'created_at',
    )

    list_display_links = ('name',)

    list_filter = (
        'is_active',
        'courses',
    )

    search_fields = ('name',)

    list_editable = ('is_active',)

    filter_horizontal = ('courses',)

    ordering = ('order', 'id')

    inlines = [SectionInline]

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'name',
                    'courses',
                    'order',
                    'is_active',
                )
            }
        ),

        (
            'Details',
            {
                'fields': ('description',),
                'classes': ('collapse',),
            }
        ),
    )

    def order_badge(self, obj):
        return format_html(
            '<span class="order-badge">{}</span>',
            obj.order
        )

    order_badge.short_description = '#'
    order_badge.admin_order_field = 'order'

    def courses_list(self, obj):
        items = [
            f'<span class="course-chip">{c.name}</span>'
            for c in obj.courses.all()
        ]

        return mark_safe(' '.join(items)) if items else '—'

    courses_list.short_description = 'Courses'

    def lecture_count(self, obj):
        total = Lecture.objects.filter(
            section__subject=obj
        ).count()

        return format_html(
            '<strong>{}</strong> lectures',
            total
        )

    lecture_count.short_description = 'Lectures'

    class Media:
        css = {
            'all': (
                'admin/css/base.css',
            )
        }


# ─────────────────────────────────────────────
# SECTION ADMIN
# ─────────────────────────────────────────────
@admin.register(Section)
class SectionAdmin(AdminStyleMixin, admin.ModelAdmin):

    list_display = (
        'order_badge',
        'title',
        'subject',
        'lecture_count',
        'created_at',
    )

    list_filter = (
        'subject__courses',
        'subject',
    )

    search_fields = (
        'title',
        'subject__name',
    )

    ordering = (
        'subject',
        'order',
        'id',
    )

    inlines = [LectureInline]

    def order_badge(self, obj):
        return format_html(
            '<span class="order-badge">{}</span>',
            obj.order
        )

    order_badge.short_description = '#'

    def lecture_count(self, obj):
        return obj.lectures.count()

    lecture_count.short_description = 'Lectures'


# ─────────────────────────────────────────────
# LECTURE ADMIN
# ─────────────────────────────────────────────
@admin.register(Lecture)
class LectureAdmin(AdminStyleMixin, admin.ModelAdmin):

    list_display = (
        'order_badge',
        'title',
        'section',
        'subject_name',
        'duration_display',
        'is_preview',
        'video_preview',
        'created_at',
    )

    list_filter = (
        'is_preview',
        'section__subject__courses',
        'section__subject',
    )

    search_fields = (
        'title',
        'section__title',
        'section__subject__name',
    )

    list_editable = ('is_preview',)

    ordering = (
        'section__subject__order',
        'section__order',
        'order',
        'id',
    )

    readonly_fields = (
        'embed_preview',
        'video_id_display',
    )

    fieldsets = (
        (
            'Lecture Info',
            {
                'fields': (
                    'title',
                    'section',
                    'order',
                    'is_preview',
                )
            }
        ),

        (
            'Video',
            {
                'fields': (
                    'youtube_embed_url',
                    'video_id_display',
                    'embed_preview',
                    'duration',
                )
            }
        ),

        (
            'Content',
            {
                'fields': ('description',),
                'classes': ('collapse',),
            }
        ),
    )

    def order_badge(self, obj):
        return format_html(
            '<span class="order-badge">{}</span>',
            obj.order
        )

    order_badge.short_description = '#'

    def subject_name(self, obj):
        return obj.section.subject.name

    subject_name.short_description = 'Subject'

    def duration_display(self, obj):
        return obj.duration_display() or '—'

    duration_display.short_description = 'Duration'

    def video_preview(self, obj):

        vid = obj.youtube_video_id

        if not vid:
            return '—'

        thumb = f"https://img.youtube.com/vi/{vid}/default.jpg"

        return format_html(
            '<img src="{}" '
            'class="admin-thumb" '
            'style="width:90px;height:50px;" />',
            thumb
        )

    video_preview.short_description = 'Thumbnail'

    def video_id_display(self, obj):

        vid = obj.youtube_video_id

        if not vid:
            return '—'

        return format_html(
            '<code style="font-size:13px;">{}</code>',
            vid
        )

    video_id_display.short_description = 'Video ID'

    def embed_preview(self, obj):

        if not obj.youtube_video_id:
            return '—'

        return format_html(
            '<div class="video-frame">'
            '<iframe '
            'src="{}" '
            'frameborder="0" '
            'allowfullscreen>'
            '</iframe>'
            '</div>',
            obj.embed_url
        )

    embed_preview.short_description = 'Preview'


# ─────────────────────────────────────────────
# ENROLLMENT ADMIN
# ─────────────────────────────────────────────
@admin.register(Enrollment)
class EnrollmentAdmin(AdminStyleMixin, admin.ModelAdmin):

    list_display = (
        'user',
        'course',
        'enrolled_at',
        'progress_bar',
    )

    list_filter = (
        'course',
        'enrolled_at',
    )

    search_fields = (
        'user__username',
        'user__email',
        'course__name',
    )

    date_hierarchy = 'enrolled_at'

    raw_id_fields = ('user',)

    def progress_bar(self, obj):

        total = Lecture.objects.filter(
            section__subject__courses=obj.course
        ).count()

        if not total:
            return '—'

        completed = LectureProgress.objects.filter(
            user=obj.user,
            lecture__section__subject__courses=obj.course,
            completed=True
        ).count()

        pct = int((completed / total) * 100)

        if pct == 100:
            color = '#28a745'
        elif pct >= 50:
            color = '#1a73e8'
        else:
            color = '#ffc107'

        return format_html(
            '<div class="progress-wrap">'
            '<div class="progress-bar" '
            'style="width:{}%;background:{};"></div>'
            '</div>'
            '<small>{}/{} ({}%)</small>',
            pct,
            color,
            completed,
            total,
            pct
        )

    progress_bar.short_description = 'Progress'


# ─────────────────────────────────────────────
# LECTURE PROGRESS ADMIN
# ─────────────────────────────────────────────
@admin.register(LectureProgress)
class LectureProgressAdmin(AdminStyleMixin, admin.ModelAdmin):

    list_display = (
        'user',
        'lecture',
        'completed_icon',
        'watched_at',
    )

    list_filter = (
        'completed',
        'lecture__section__subject__courses',
    )

    search_fields = (
        'user__username',
        'lecture__title',
    )

    raw_id_fields = (
        'user',
        'lecture',
    )

    def completed_icon(self, obj):

        if obj.completed:
            return mark_safe(
                '<span style="color:#28a745;font-size:18px;">✓</span>'
            )

        return mark_safe(
            '<span style="color:#dc3545;font-size:18px;">○</span>'
        )

    completed_icon.short_description = 'Done'


# ─────────────────────────────────────────────
# SUBJECT INLINE FOR COURSE
# ─────────────────────────────────────────────
class SubjectInlineForCourse(admin.TabularInline):

    model = Subject.courses.through

    extra = 0

    verbose_name = "Subject"

    verbose_name_plural = "Subjects"

    can_delete = True

    autocomplete_fields = ('subject',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('subject')


# ─────────────────────────────────────────────
# COURSE ADMIN
# ─────────────────────────────────────────────
@admin.register(Course)
class CourseAdmin(AdminStyleMixin, admin.ModelAdmin):

    list_display = (
        'thumbnail_preview',
        'name',
        'slug',
        'subject_count',
        'total_lectures_count',
        'enrollment_count',
        'is_active',
    )

    list_display_links = ('name',)

    list_filter = (
        'is_active',
        'created_at',
    )

    search_fields = (
        'name',
        'tags',
    )

    list_editable = ('is_active',)

    readonly_fields = (
        'slug',
        'thumbnail_preview_large',
        'seo_excerpt',
        'total_lectures_count',
        'enrollment_count',
    )

    inlines = [SubjectInlineForCourse]

    fieldsets = (
        (
            'Course Details',
            {
                'fields': (
                    'name',
                    'slug',
                    'thumbnail',
                    'thumbnail_preview_large',
                    'tags',
                    'is_active',
                )
            }
        ),

        (
            'Content',
            {
                'fields': ('description',)
            }
        ),

        (
            'SEO',
            {
                'fields': ('seo_excerpt',),
                'classes': ('collapse',),
            }
        ),

        (
            'Statistics',
            {
                'fields': (
                    'total_lectures_count',
                    'enrollment_count',
                ),
                'classes': ('collapse',),
            }
        ),
    )

    def thumbnail_preview(self, obj):

        if not obj.thumbnail:
            return '—'

        return format_html(
            '<img src="{}" '
            'class="admin-thumb" '
            'style="width:70px;height:45px;" />',
            obj.thumbnail.url
        )

    thumbnail_preview.short_description = 'Cover'

    def thumbnail_preview_large(self, obj):

        if not obj.thumbnail:
            return '—'

        return format_html(
            '<img src="{}" '
            'style="max-width:320px;border-radius:12px;" />',
            obj.thumbnail.url
        )

    thumbnail_preview_large.short_description = 'Preview'

    def subject_count(self, obj):
        return obj.subjects.filter(is_active=True).count()

    subject_count.short_description = 'Subjects'

    def total_lectures_count(self, obj):
        return obj.total_lectures()

    total_lectures_count.short_description = 'Lectures'

    def enrollment_count(self, obj):

        total = obj.enrollments.count()

        return format_html(
            '<strong>{}</strong> students',
            total
        )

    enrollment_count.short_description = 'Enrollments'