"""
exams/admin.py
"""
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .forms import ExamAdminForm, ParagraphAdminForm, QuestionAdminForm
from .models import Exam, ExamAttempt, Paragraph, Question, QuestionAttempt, Section
from .utils import invalidate_exam_cache


# Inline classes
class SectionInline(admin.TabularInline):
    model       = Section
    extra       = 1
    show_change_link = True
    fields      = ['title', 'order', 'override_scoring',
                   'custom_correct_marks', 'custom_negative_marks', 'custom_has_negative']


class ParagraphInline(admin.StackedInline):
    model  = Paragraph
    form   = ParagraphAdminForm
    extra  = 0
    show_change_link = True
    fields = ['title', 'content', 'order']


class QuestionInline(admin.TabularInline):
    model  = Question
    extra  = 0
    show_change_link = True
    fields = ['question_text', 'correct_option', 'marks',
              'use_custom_marks', 'paragraph', 'order']
    readonly_fields = ['question_text']


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    form         = ExamAdminForm
    list_display = [
        'title', 'course', 'start_date', 'end_date',
        'duration_display', 'q_count', 'attempt_count',
        'result_mode', 'is_active', 'action_links',
    ]
    list_filter  = ['course', 'is_active', 'has_negative_marking', 'result_mode']
    search_fields= ['title', 'course__title']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    inlines      = [SectionInline]
    actions      = ['publish_results_now', 'hide_results', 'recalculate_all_scores',
                    'invalidate_cache']

    fieldsets = (
        ('Basic Info', {
            'fields': ('course', 'title', 'description', 'instructions',
                       'slug', 'is_active'),
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date', 'duration_minutes',
                       'make_public', 'make_public_after'),
        }),
        ('Scoring Defaults', {
            'fields': ('correct_marks', 'negative_marks', 'has_negative_marking'),
            'description': 'Section/question-level overrides will supersede these.',
        }),
        ('Result Visibility', {
            'fields': ('result_mode', 'result_publish_time'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # ── Display helpers ───────────────────────────────────────────────────────

    @admin.display(description='Duration')
    def duration_display(self, obj):
        if obj.duration_minutes:
            return f"{obj.duration_minutes} min"
        return "Unlimited" if not obj.end_date else "Until end date"

    @admin.display(description='Questions')
    def q_count(self, obj):
        return obj.questions.count()

    @admin.display(description='Submissions')
    def attempt_count(self, obj):
        return obj.attempts.filter(is_submitted=True).count()

    @admin.display(description='Links')
    def action_links(self, obj):
        detail = reverse('exams:exam_detail', kwargs={'slug': obj.slug})
        imp    = reverse('exams:import_exam_page')
        return format_html(
            '<a href="{}" target="_blank">View</a> | '
            '<a href="{}">Import JSON</a>',
            detail, imp
        )

    # ── Admin actions ─────────────────────────────────────────────────────────

    @admin.action(description='Publish results now (set mode → after_end)')
    def publish_results_now(self, request, queryset):
        queryset.update(result_mode='after_end')
        for e in queryset:
            invalidate_exam_cache(e.pk)
        self.message_user(request, f"Results published for {queryset.count()} exam(s).")

    @admin.action(description='Hide results (set mode → hidden)')
    def hide_results(self, request, queryset):
        queryset.update(result_mode='hidden')
        for e in queryset:
            invalidate_exam_cache(e.pk)
        self.message_user(request, f"Results hidden for {queryset.count()} exam(s).")

    @admin.action(description='Recalculate scores for all submitted attempts')
    def recalculate_all_scores(self, request, queryset):
        n = 0
        for exam in queryset:
            for attempt in exam.attempts.filter(is_submitted=True):
                attempt.calculate_score()
                n += 1
            invalidate_exam_cache(exam.pk)
        self.message_user(request, f"Recalculated {n} attempt(s).")

    @admin.action(description='Invalidate exam cache')
    def invalidate_cache(self, request, queryset):
        for e in queryset:
            invalidate_exam_cache(e.pk)
        self.message_user(request, "Cache cleared.")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidate_exam_cache(obj.pk)

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display  = ['title', 'exam', 'order', 'override_scoring',
                     'effective_correct', 'effective_negative', 'q_count']
    list_filter   = ['exam__course', 'override_scoring']
    search_fields = ['title', 'exam__title']
    inlines       = [ParagraphInline, QuestionInline]

    @admin.display(description='Correct Marks')
    def effective_correct(self, obj):
        return obj.get_correct_marks()

    @admin.display(description='Neg Marks')
    def effective_negative(self, obj):
        return obj.get_negative_marks() if obj.get_has_negative() else '—'

    @admin.display(description='Questions')
    def q_count(self, obj):
        return obj.questions.count()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidate_exam_cache(obj.exam_id)


# Paragraph
@admin.register(Paragraph)
class ParagraphAdmin(admin.ModelAdmin):
    form          = ParagraphAdminForm
    list_display  = ['__str__', 'section', 'order', 'q_count']
    list_filter   = ['section__exam']
    search_fields = ['title', 'content']

    @admin.display(description='Questions')
    def q_count(self, obj):
        return obj.questions.count()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidate_exam_cache(obj.section.exam_id)


# Question
@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form          = QuestionAdminForm
    list_display  = ['short_text', 'exam', 'section', 'paragraph',
                     'correct_option', 'marks', 'use_custom_marks', 'order']
    list_filter   = ['exam', 'section', 'use_custom_marks']
    search_fields = ['question_text']
    list_editable = ['order', 'correct_option', 'marks']
    ordering      = ['exam', 'section__order', 'order']

    @admin.display(description='Question')
    def short_text(self, obj):
        import re
        text = re.sub(r'<[^>]+>', '', obj.question_text)
        return text[:80] + '…' if len(text) > 80 else text

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        invalidate_exam_cache(obj.exam_id)


# Exam Attempt
@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display  = ['student', 'exam', 'score', 'negative_score',
                     'correct_count', 'wrong_count', 'unattempted_count',
                     'is_submitted', 'started_at']
    list_filter   = ['exam', 'is_submitted']
    search_fields = ['student__username', 'exam__title']
    readonly_fields = ['score', 'negative_score', 'correct_count',
                       'wrong_count', 'unattempted_count', 'started_at']
    actions       = ['recalculate']

    @admin.action(description='Recalculate selected scores')
    def recalculate(self, request, queryset):
        for a in queryset:
            a.calculate_score()
        self.message_user(request, f"Recalculated {queryset.count()} attempt(s).")