"""
exams/importers.py
──────────────────
Import a full exam structure from a validated JSON dict.
All DB writes happen inside a single atomic transaction so the DB stays
consistent even on partial failure.
"""
from __future__ import annotations

from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from apps.pages.models import Course
from .models import Exam, Section, Paragraph, Question


@transaction.atomic
def import_exam_from_json(data: dict) -> Exam:
    """
    Creates an Exam (with Sections, Paragraphs, Questions) from a JSON dict.
    Raises ValueError with a human-readable message on any validation failure.
    """
    data.pop('_instructions', None)  # strip docs key if present

    # ── Course ────────────────────────────────────────────────────────────────
    course_title = (data.get('course_title') or '').strip()
    if not course_title:
        raise ValueError("`course_title` is required.")
    try:
        course = Course.objects.get(title__iexact=course_title)
    except Course.DoesNotExist:
        raise ValueError(f"Course '{course_title}' not found. Create it in the admin first.")

    # ── Exam meta ─────────────────────────────────────────────────────────────
    ed = data.get('exam') or {}

    def _dt(field):
        v = ed.get(field)
        if not v:
            return None
        parsed = parse_datetime(str(v))
        if parsed is None:
            raise ValueError(f"Cannot parse date '{v}' for field '{field}'. "
                             f"Use ISO-8601: 2024-01-15T10:00:00")
        return parsed

    start_date = _dt('start_date') or timezone.now()
    end_date   = _dt('end_date')
    rpt        = _dt('result_publish_time')

    result_mode = ed.get('result_mode', 'after_end')
    if result_mode not in ('hidden', 'after_end', 'auto', 'manual'):
        result_mode = 'after_end'

    exam = Exam.objects.create(
        course              = course,
        title               = ed.get('title', 'Imported Exam'),
        description         = ed.get('description', ''),
        instructions        = ed.get('instructions', ''),
        start_date          = start_date,
        end_date            = end_date,
        duration_minutes    = ed.get('duration_minutes') or None,
        correct_marks       = float(ed.get('correct_marks',  1.0)),
        negative_marks      = float(ed.get('negative_marks', 0.0)),
        has_negative_marking= bool( ed.get('has_negative_marking', False)),
        result_mode         = result_mode,
        result_publish_time = rpt,
        make_public_after   = bool(ed.get('make_public_after', False)),
    )

    # ── Sections → Paragraphs → Questions ────────────────────────────────────
    total_q = 0
    for sec_data in data.get('sections', []):
        override = bool(sec_data.get('override_scoring', False))

        cm  = sec_data.get('correct_marks')
        nm  = sec_data.get('negative_marks')
        hn  = sec_data.get('has_negative_marking')

        section = Section.objects.create(
            exam             = exam,
            title            = sec_data.get('title', 'Section'),
            description      = sec_data.get('description', ''),
            order            = int(sec_data.get('order', 0)),
            override_scoring = override,
            custom_correct_marks  = float(cm) if cm is not None and override else None,
            custom_negative_marks = float(nm) if nm is not None and override else None,
            custom_has_negative   = bool(hn) if hn is not None and override else None,
        )

        # Paragraphs — build a map by `order` for question linking
        para_map: dict[int, Paragraph] = {}
        for para_data in sec_data.get('paragraphs', []):
            para = Paragraph.objects.create(
                section = section,
                title   = para_data.get('title', ''),
                content = para_data.get('content', ''),
                order   = int(para_data.get('order', 0)),
            )
            para_map[para_data.get('order', 0)] = para

        # Questions
        for q_data in sec_data.get('questions', []):
            para_order = q_data.get('paragraph_order')
            paragraph  = para_map.get(para_order) if para_order is not None else None

            correct = str(q_data.get('correct_option', ''))
            if correct not in ('1', '2', '3', '4', ''):
                correct = ''   # tolerate bad values gracefully

            Question.objects.create(
                exam             = exam,
                section          = section,
                paragraph        = paragraph,
                question_text    = q_data.get('question_text', ''),
                option_one       = q_data.get('option_one',   ''),
                option_two       = q_data.get('option_two',   ''),
                option_three     = q_data.get('option_three', ''),
                option_four      = q_data.get('option_four',  ''),
                correct_option   = correct,
                explanation      = q_data.get('explanation', ''),
                marks            = float(q_data.get('marks', 1.0)),
                use_custom_marks = bool( q_data.get('use_custom_marks', False)),
                order            = int(  q_data.get('order', total_q + 1)),
            )
            total_q += 1

    return exam