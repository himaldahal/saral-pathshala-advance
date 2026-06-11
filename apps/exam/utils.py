"""
exams/utils.py
──────────────
Caching helpers + structured exam data builder.

Compatible with any Django cache backend, including Redis and Memcached,
because all cached values are plain JSON-serialisable dicts/lists — no
ORM model instances are stored in the cache.
"""

from __future__ import annotations

from collections import defaultdict

from django.core.cache import cache
from django.utils import timezone

EXAM_CACHE_TTL = 600  # 10 min — question/section data (rarely changes)
LIST_CACHE_TTL = 60  # 1 min  — per-user exam list
RESULT_CACHE_TTL = 120  # 2 min  — leaderboard


# ─────────────────────────────────────────────────────────────────────────────
# Cache-key helpers  (exported so views can import them)
# ─────────────────────────────────────────────────────────────────────────────


def _exam_data_key(exam_pk: int) -> str:
    return f"exam_data_{exam_pk}"


def _exam_list_key(user_pk: int) -> str:
    return f"exam_list_{user_pk}"


def _lb_key(exam_pk: int) -> str:
    return f"leaderboard_{exam_pk}"


def invalidate_exam_cache(exam_pk: int) -> None:
    """Delete all cache entries that depend on a given exam."""
    cache.delete(_exam_data_key(exam_pk))
    cache.delete(_lb_key(exam_pk))


# ─────────────────────────────────────────────────────────────────────────────
# Paragraph-grouped question builder
# ─────────────────────────────────────────────────────────────────────────────


def _build_question_groups(questions: list, para_map: dict) -> list:
    """
    Group a flat ordered list of question dicts by their paragraph.

    Returns:
        [{'paragraph': dict|None, 'questions': [question_dict, ...]}, ...]
    """
    groups: list = []
    _SENTINEL = object()  # never equals None or a real paragraph id
    current_pid = _SENTINEL

    for q in questions:
        pid = q["paragraph_id"]
        if pid != current_pid:
            current_pid = pid
            groups.append(
                {
                    "paragraph": para_map.get(pid) if pid else None,
                    "questions": [],
                }
            )
        groups[-1]["questions"].append(q)

    return groups


# ─────────────────────────────────────────────────────────────────────────────
# Main exam data loader  (cached)
# ─────────────────────────────────────────────────────────────────────────────


def get_exam_data(exam) -> dict:
    """
    Return a fully-structured, JSON-serialisable dict ready for template
    rendering.  Cached per exam for EXAM_CACHE_TTL seconds.

    All values stored in the cache are plain Python primitives (str, int,
    float, bool, list, dict, None) so the result is safe for Redis,
    Memcached, and LocMemCache alike.

    Structure:
    {
      'total_questions': int,
      'sections': [
        {
          'id', 'title', 'description', 'order',
          'correct_marks', 'negative_marks', 'has_negative',
          'paragraphs': [{id, title, content, order}, ...],
          'question_groups': [
            {
              'paragraph': {id, title, content, order} | None,
              'questions': [
                {id, global_num, text, options, correct, marks, neg_marks,
                 order, paragraph_id, explanation}
              ]
            }
          ],
          'questions_flat': [same question dicts as above]
        }
      ]
    }

    Note: 'correct' and 'explanation' are included here (full data).
    The view layer is responsible for stripping them before passing the
    data to the exam attempt template.
    """
    key = _exam_data_key(exam.pk)
    data = cache.get(key)
    if data is not None:
        return data

    from .models import Paragraph, Question, Section

    # Sequential DB fetches (thread-safe) 
    # The previous ThreadPoolExecutor approach shared Django DB connections
    # across threads without proper setup/teardown, which can cause
    # "connection already closed" errors under load.  Three small queries
    # issued sequentially are cheap and correct.

    sections = list(Section.objects.filter(exam=exam).order_by("order", "id"))

    paras_by_section: dict[int, list] = defaultdict(list)
    for p in Paragraph.objects.filter(section__exam=exam).order_by(
        "section_id", "order", "id"
    ):
        paras_by_section[p.section_id].append(
            {
                "id": p.id,
                "title": p.title,
                "content": p.content,
                "order": p.order,
            }
        )

    qs_by_section: dict[int, list] = defaultdict(list)
    for q in (
        Question.objects.filter(exam=exam)
        .select_related("section", "paragraph")
        .order_by("section__order", "order", "id")
    ):
        qs_by_section[q.section_id].append(
            {
                "id": q.id,
                "global_num": 0,  # filled in below
                "text": q.question_text,
                "options": q.get_options(),
                "correct": q.correct_option,
                "marks": q.get_correct_marks(),
                "neg_marks": q.get_negative_marks(),
                "order": q.order,
                "paragraph_id": q.paragraph_id,
                "explanation": q.explanation,
            }
        )

    # ── Assign global question numbers + build sections ───────────────────────
    g_num = 1
    built = []

    for sec in sections:
        paras = paras_by_section.get(sec.id, [])
        para_map = {p["id"]: p for p in paras}
        qs = qs_by_section.get(sec.id, [])

        for q in qs:
            q["global_num"] = g_num
            g_num += 1

        built.append(
            {
                "id": sec.id,
                "title": sec.title,
                "description": sec.description,
                "order": sec.order,
                "correct_marks": sec.get_correct_marks(),
                "negative_marks": sec.get_negative_marks(),
                "has_negative": sec.get_has_negative(),
                "paragraphs": paras,
                "question_groups": _build_question_groups(qs, para_map),
                "questions_flat": qs,  # flat list kept for palette rendering
            }
        )

    data = {"total_questions": g_num - 1, "sections": built}
    cache.set(key, data, EXAM_CACHE_TTL)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Leaderboard  (cached)
# ─────────────────────────────────────────────────────────────────────────────


def get_leaderboard(exam, limit: int = 50) -> list:
    """
    Return the top-N submitted attempts for an exam as a list of plain dicts.

    Storing dicts (not ORM instances) makes this safe for Redis/Memcached
    which require picklable / JSON-serialisable values.
    """
    key = _lb_key(exam.pk)
    data = cache.get(key)
    if data is not None:
        return data

    from .models import ExamAttempt

    rows = (
        ExamAttempt.objects.filter(exam=exam, is_submitted=True)
        .select_related("student")
        .order_by("-score")[:limit]
    )

    # FIX: serialise to plain dicts so Redis/Memcached can store them.
    data = [
        {
            "student_id": a.student_id,
            "student_name": getattr(a.student, "get_full_name", lambda: "")()
            or a.student.email,
            "student_email": a.student.email,
            "score": a.score,
            "correct_count": a.correct_count,
            "wrong_count": a.wrong_count,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        }
        for a in rows
    ]

    cache.set(key, data, RESULT_CACHE_TTL)
    return data
