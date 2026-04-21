from django.db import models
from django.utils.text import slugify
from django.utils.html import strip_tags
from django.utils.functional import cached_property
import re

from apps.pages.utils import generate_random_slug


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
        """
        Generate SEO-friendly description:
        - Remove HTML
        - Normalize spaces
        - Truncate to ~155 chars
        """
        if not self.description:
            return ""

        # Remove HTML tags
        clean_text = strip_tags(self.description)

        # Normalize whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        # Truncate safely
        return clean_text[:155].rstrip() + ("..." if len(clean_text) > 155 else "")

    def save(self, *args, **kwargs):
        # Generate slug
        if not self.slug:
            base_slug = slugify(self.name)[:30]
            self.slug = f"{base_slug}-{generate_random_slug(4)}"

        # Auto-generate SEO excerpt only if empty
        if not self.seo_excerpt:
            self.seo_excerpt = self.generate_seo_excerpt()

        super().save(*args, **kwargs)