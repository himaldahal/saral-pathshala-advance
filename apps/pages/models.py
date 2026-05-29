from django.db import models
from django.utils.text import slugify
from django.utils.html import strip_tags
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.conf import settings

import re

from apps.pages.utils import generate_random_slug


# =========================================================
# COURSE
# =========================================================

class Course(models.Model):
    thumbnail   = models.ImageField(upload_to='courses')
    name        = models.CharField(max_length=120, unique=True)
    slug        = models.SlugField(max_length=50, unique=True, blank=True)

    tags        = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    seo_excerpt = models.CharField(max_length=160, blank=True)

    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Course"
        verbose_name_plural = "Courses"

    def __str__(self):
        return self.name

    def generate_seo_excerpt(self):
        if not self.description:
            return ""
        clean_text = strip_tags(self.description)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        return clean_text[:155].rstrip() + ("..." if len(clean_text) > 155 else "")

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)[:30]
            self.slug = f"{base_slug}-{generate_random_slug(4)}"
        if not self.seo_excerpt:
            self.seo_excerpt = self.generate_seo_excerpt()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('course_detail', kwargs={'slug': self.slug})

    def total_lectures(self):
        return Lecture.objects.filter(section__subject__courses=self).count()

    def total_subjects(self):
        return self.subjects.filter(is_active=True).count()

    def get_first_lecture(self):
        """Return the very first lecture of this course."""
        return (
            Lecture.objects
            .filter(section__subject__courses=self)
            .order_by('section__subject__order', 'section__subject__id',
                      'section__order', 'section__id',
                      'order', 'id')
            .first()
        )

# SUBJECT
class Subject(models.Model):
    courses = models.ManyToManyField(
        Course,
        related_name='subjects'
    )

    name        = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    order       = models.PositiveIntegerField(default=0, db_index=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return self.name

    def lecture_count(self):
        return Lecture.objects.filter(section__subject=self).count()

# SECTION
class Section(models.Model):
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='sections'
    )

    title   = models.CharField(max_length=120, blank=True, null=True)
    order   = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Section"
        verbose_name_plural = "Sections"

    def __str__(self):
        return self.title or f"Section #{self.pk} - {self.subject.name}"

    def lecture_count(self):
        return self.lectures.count()


# =========================================================
# LECTURE
# =========================================================

class Lecture(models.Model):
    section           = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='lectures'
    )

    title             = models.CharField(max_length=255)
    youtube_embed_url = models.URLField(max_length=500)
    description       = models.TextField(blank=True)
    duration          = models.DurationField(blank=True, null=True)
    is_preview        = models.BooleanField(default=False)
    order             = models.PositiveIntegerField(default=0, db_index=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Lecture"
        verbose_name_plural = "Lectures"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        allowed = ["youtube.com", "www.youtube.com", "youtu.be"]
        if not any(domain in self.youtube_embed_url for domain in allowed):
            raise ValidationError({
                "youtube_embed_url": "Only YouTube URLs are allowed."
            })

    def get_absolute_url(self):
        first_course = self.section.subject.courses.first()
        if not first_course:
            return "#"
        return reverse(
            "lecture_detail",
            kwargs={"slug": f"{first_course.slug}-{self.pk}"}
        )

    @property
    def youtube_video_id(self):
        patterns = [
            r"youtu\.be\/([a-zA-Z0-9_-]+)",
            r"youtube\.com\/watch\?v=([a-zA-Z0-9_-]+)",
            r"youtube\.com\/embed\/([a-zA-Z0-9_-]+)",
            r"youtube\.com\/shorts\/([a-zA-Z0-9_-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, self.youtube_embed_url)
            if match:
                return match.group(1)
        return None

    @property
    def embed_url(self):
        """Privacy-enhanced embed URL with custom player params."""
        video_id = self.youtube_video_id
        if not video_id:
            return ""
        return (
            f"https://www.youtube-nocookie.com/embed/{video_id}"
            f"?enablejsapi=1&controls=0&modestbranding=1&rel=0"
            f"&showinfo=0&iv_load_policy=3&playsinline=1&fs=0"
            f"&disablekb=1&origin={getattr(settings, 'SITE_URL', '')}"
        )

    def duration_display(self):
        if not self.duration:
            return ""
        total_seconds = int(self.duration.total_seconds())
        hours   = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours:
            return f"{hours}:{minutes:02}:{seconds:02}"
        return f"{minutes}:{seconds:02}"

    def get_next_lecture(self, course):
        """Get the next lecture in this course."""
        all_lectures = list(
            Lecture.objects
            .filter(section__subject__courses=course)
            .order_by('section__subject__order', 'section__subject__id',
                      'section__order', 'section__id',
                      'order', 'id')
            .values_list('id', flat=True)
        )
        try:
            idx = all_lectures.index(self.pk)
            if idx + 1 < len(all_lectures):
                return Lecture.objects.get(pk=all_lectures[idx + 1])
        except (ValueError, Lecture.DoesNotExist):
            pass
        return None

    def get_prev_lecture(self, course):
        """Get the previous lecture in this course."""
        all_lectures = list(
            Lecture.objects
            .filter(section__subject__courses=course)
            .order_by('section__subject__order', 'section__subject__id',
                      'section__order', 'section__id',
                      'order', 'id')
            .values_list('id', flat=True)
        )
        try:
            idx = all_lectures.index(self.pk)
            if idx > 0:
                return Lecture.objects.get(pk=all_lectures[idx - 1])
        except (ValueError, Lecture.DoesNotExist):
            pass
        return None


# =========================================================
# ENROLLMENT
# =========================================================

class Enrollment(models.Model):
    user   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'course')
        ordering = ['-enrolled_at']
        verbose_name = "Enrollment"
        verbose_name_plural = "Enrollments"

    def __str__(self):
        return f"{self.user} → {self.course}"


# =========================================================
# LECTURE PROGRESS
# =========================================================

class LectureProgress(models.Model):
    user       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lecture_progress'
    )
    lecture    = models.ForeignKey(
        Lecture,
        on_delete=models.CASCADE,
        related_name='progress'
    )
    completed  = models.BooleanField(default=False)
    watched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'lecture')
        verbose_name = "Lecture Progress"
        verbose_name_plural = "Lecture Progress"

    def __str__(self):
        status = "✓" if self.completed else "○"
        return f"{status} {self.user} → {self.lecture}"