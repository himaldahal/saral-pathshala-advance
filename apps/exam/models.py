from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.pages.models import Course


# EXAM
class Exam(models.Model):
    RESULT_MODE_CHOICES = [
        ("hidden", "Hidden | Never show results"),
        ("after_end", "After End | Show once exam ends"),
        ("auto", "Scheduled | Show at specific date/time"),
        ("manual", "Manual | Admin toggles visibility"),
    ]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="exams")
    title = models.CharField(max_length=255)
    description = models.TextField(
        blank=True, help_text="Supports HTML / LaTeX / images."
    )
    instructions = models.TextField(
        blank=True, help_text="Shown on the exam start page."
    )

    # Scheduling
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(
        null=True, blank=True, help_text="Leave blank for no hard deadline."
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Personal time-limit in minutes. Leave blank for unlimited.",
    )

    # Access control
    make_public = models.BooleanField(
        default=False,
        help_text="Always visible regardless of dates (e.g. practice exam).",
    )
    make_public_after = models.BooleanField(
        default=False,
        help_text="Allow students to attempt the exam even after end_date.",
    )

    # Exam-level scoring defaults
    correct_marks = models.FloatField(
        default=1.0, help_text="Marks per correct answer."
    )
    negative_marks = models.FloatField(
        default=0.0, help_text="Marks deducted per wrong answer (positive value)."
    )
    has_negative_marking = models.BooleanField(default=False)

    # Result visibility
    result_mode = models.CharField(
        max_length=20, choices=RESULT_MODE_CHOICES, default="after_end"
    )
    result_publish_time = models.DateTimeField(
        null=True, blank=True, help_text="Only used when result_mode = 'auto'."
    )

    slug = models.SlugField(max_length=500, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Exam"
        verbose_name_plural = "Exams"

    # Lifecycle

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f"{slugify(self.course.name)}-{slugify(self.title)}"
            slug, n = base, 1
            while Exam.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)
        cache.clear()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        cache.clear()

    # Status helpers
    
    @property
    def is_live(self):
        return self.has_started() and not self.has_ended()

    @property
    def questions_count(self):
        return self.total_questions()

    def has_started(self):
        return timezone.now() >= self.start_date

    def has_ended(self):
        return bool(self.end_date) and timezone.now() > self.end_date

    def is_accessible(self, user=None):
        """Can this user open/attempt the exam right now?"""
        if not self.is_active:
            return False
        if user and (user.is_staff or user.is_superuser):
            return True
        if self.make_public:
            return True
        now = timezone.now()
        if now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return self.make_public_after
        return True

    def is_results_visible(self):
        mode = self.result_mode
        if mode == "hidden":
            return False
        if mode == "after_end":
            return self.has_ended()
        if mode == "auto" and self.result_publish_time:
            return timezone.now() >= self.result_publish_time
        # 'manual' | handled by admin toggling result_mode to 'after_end'
        return False

    def total_questions(self):
        return self.questions.count()

    def total_marks(self):
        from django.db.models import Sum

        agg = self.questions.aggregate(t=Sum("marks"))
        return agg["t"] or 0

    def __str__(self):
        return f"{self.title} ({self.course.name})"


class Section(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    # Optional per-section scoring override
    override_scoring = models.BooleanField(
        default=False, help_text="Override exam-level scoring rules for this section."
    )
    custom_correct_marks = models.FloatField(null=True, blank=True)
    custom_negative_marks = models.FloatField(null=True, blank=True)
    custom_has_negative = models.BooleanField(null=True, blank=True)

    class Meta:
        unique_together = ("title", "exam")
        ordering = ["order", "id"]

    # Resolved scoring

    def get_correct_marks(self):
        if self.override_scoring and self.custom_correct_marks is not None:
            return self.custom_correct_marks
        return self.exam.correct_marks

    def get_negative_marks(self):
        if self.override_scoring and self.custom_negative_marks is not None:
            return self.custom_negative_marks
        return self.exam.negative_marks

    def get_has_negative(self):
        if self.override_scoring and self.custom_has_negative is not None:
            return self.custom_has_negative
        return self.exam.has_negative_marking

    def __str__(self):
        return f"{self.title} | {self.exam.title}"


# PARAGRAPH  (passage / reading block)


class Paragraph(models.Model):
    section = models.ForeignKey(
        Section, on_delete=models.CASCADE, related_name="paragraphs"
    )
    title = models.CharField(
        max_length=255, blank=True, help_text="Optional label, e.g. 'Passage 1'."
    )
    content = models.TextField(help_text="HTML / LaTeX / code | rendered in exam view.")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title or f"Paragraph {self.pk} ({self.section.title})"


# QUESTION


class Question(models.Model):
    OPTION_CHOICES = [
        ("1", "Option 1"),
        ("2", "Option 2"),
        ("3", "Option 3"),
        ("4", "Option 4"),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    section = models.ForeignKey(
        Section, on_delete=models.CASCADE, related_name="questions"
    )
    paragraph = models.ForeignKey(
        Paragraph,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        help_text="Link to a reading passage if applicable.",
    )

    question_text = models.TextField(
        help_text="Supports LaTeX ($$...$$), HTML, <pre> code blocks."
    )
    option_one = models.TextField(blank=True)
    option_two = models.TextField(blank=True)
    option_three = models.TextField(blank=True)
    option_four = models.TextField(blank=True)
    correct_option = models.CharField(
        max_length=1, choices=OPTION_CHOICES, blank=True, null=True
    )
    explanation = models.TextField(
        blank=True,
        help_text="Shown after results are published. Supports HTML / LaTeX.",
    )

    # Per-question mark override (useful for IOE-style variable marking)
    marks = models.FloatField(default=1.0)
    use_custom_marks = models.BooleanField(
        default=False,
        help_text="Use this question's marks instead of section/exam defaults.",
    )

    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["section__order", "order", "id"]

    # Resolved scoring

    def get_correct_marks(self):
        return self.marks if self.use_custom_marks else self.section.get_correct_marks()

    def get_negative_marks(self):
        if not self.section.get_has_negative():
            return 0.0
        if self.use_custom_marks:
            # IOE style: 10 % of question mark
            return round(self.marks * 0.1, 4)
        return self.section.get_negative_marks()

    def get_options(self):
        opts = []
        for key, text in [
            ("1", self.option_one),
            ("2", self.option_two),
            ("3", self.option_three),
            ("4", self.option_four),
        ]:
            if text and text.strip():
                opts.append({"key": key, "text": text})
        return opts

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:70]}"


# EXAM ATTEMPT
class ExamAttempt(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_attempts"
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(default=0.0)
    negative_score = models.FloatField(default=0.0)
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    unattempted_count = models.PositiveIntegerField(default=0)
    is_submitted = models.BooleanField(default=False)

    class Meta:
        unique_together = ("student", "exam")
        ordering = ["-started_at"]

    def calculate_score(self):
        """Recalculate and persist score from question attempts, including unattempted questions."""
        # Get all questions for this exam
        questions = list(self.exam.questions.all())
        # Get all question attempts
        attempts_map = {
            qa.question_id: qa.selected_option for qa in self.question_attempts.all()
        }

        pos = neg = 0.0
        correct = wrong = unattempted = 0

        for q in questions:
            selected = attempts_map.get(q.id)
            if not selected:
                unattempted += 1
            elif selected == q.correct_option:
                pos += q.get_correct_marks()
                correct += 1
            else:
                neg += q.get_negative_marks()
                wrong += 1

        self.score = round(pos - neg, 4)
        self.negative_score = round(neg, 4)
        self.correct_count = correct
        self.wrong_count = wrong
        self.unattempted_count = unattempted
        self.save(
            update_fields=[
                "score",
                "negative_score",
                "correct_count",
                "wrong_count",
                "unattempted_count",
            ]
        )
        return self.score

    def submit(self):
        self.completed_at = timezone.now()
        self.is_submitted = True
        self.save(update_fields=["completed_at", "is_submitted"])
        self.calculate_score()

    def __str__(self):
        return f"{self.student.email} | {self.exam.title}"


# QUESTION ATTEMPT
class QuestionAttempt(models.Model):
    exam_attempt = models.ForeignKey(
        ExamAttempt, on_delete=models.CASCADE, related_name="question_attempts"
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="attempts"
    )
    selected_option = models.CharField(
        max_length=1, choices=Question.OPTION_CHOICES, blank=True, null=True
    )
    answered_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("exam_attempt", "question")

    @property
    def is_correct(self):
        if not self.selected_option:
            return None
        return self.selected_option == self.question.correct_option

    def __str__(self):
        return f"{self.exam_attempt.student.email} | Q{self.question.id}"
