"""
exams/utils.py
─────────────
Caching helpers + structured exam data builder.
Uses Django's built-in LocMemCache (no Redis required).
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.cache import cache
from django.db.models import Prefetch

EXAM_CACHE_TTL   = 300   # 5 min  | question/section data
LIST_CACHE_TTL   = 60    # 1 min  | exam list
RESULT_CACHE_TTL = 120   # 2 min  | leaderboard


# ─────────────────────────────────────────────────────────────────────────────
# Cache-key helpers
# ─────────────────────────────────────────────────────────────────────────────

def _exam_data_key(exam_pk):  return f'exam_data_{exam_pk}'
def _exam_list_key(user_pk):  return f'exam_list_{user_pk}'
def _lb_key(exam_pk):         return f'leaderboard_{exam_pk}'


def invalidate_exam_cache(exam_pk: int):
    """Delete all caches that depend on a given exam."""
    cache.delete(_exam_data_key(exam_pk))
    cache.delete(_lb_key(exam_pk))


# ─────────────────────────────────────────────────────────────────────────────
# Paragraph-grouped question builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_question_groups(questions: list, para_map: dict) -> list:
    """
    Group a flat ordered list of questions by their paragraph.
    Returns a list of dicts:
        {'paragraph': dict|None, 'questions': [question_dict, ...]}
    """
    groups: list = []
    current_pid = object()          # sentinel | never equals None or a real id

    for q in questions:
        pid = q['paragraph_id']
        if pid != current_pid:
            current_pid = pid
            groups.append({
                'paragraph': para_map.get(pid) if pid else None,
                'questions': [],
            })
        groups[-1]['questions'].append(q)

    return groups


# ─────────────────────────────────────────────────────────────────────────────
# Main exam data loader  (cached)
# ─────────────────────────────────────────────────────────────────────────────

def get_exam_data(exam) -> dict:
    """
    Return a fully-structured dict ready for template rendering.
    Cached per exam for EXAM_CACHE_TTL seconds.

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
              'paragraph': {id, title, content} | None,
              'questions': [
                {id, global_num, text, options, correct, marks, neg_marks,
                 order, paragraph_id, explanation}
              ]
            }
          ]
        }
      ]
    }
    """
    key  = _exam_data_key(exam.pk)
    data = cache.get(key)
    if data is not None:
        return data

    from .models import Section, Paragraph, Question

    # ── Parallel DB fetches via threads ──────────────────────────────────────
    sections_result: list = []
    paragraphs_result: dict = {}   # section_id → [para_dict]
    questions_result: dict = {}    # section_id → [q_dict]

    def fetch_sections():
        return list(
            Section.objects.filter(exam=exam).order_by('order', 'id')
        )

    def fetch_paragraphs():
        paras = Paragraph.objects.filter(section__exam=exam).order_by('section_id', 'order', 'id')
        result = defaultdict(list)
        for p in paras:
            result[p.section_id].append({
                'id': p.id, 'title': p.title,
                'content': p.content, 'order': p.order,
            })
        return dict(result)

    def fetch_questions():
        qs = (
            Question.objects
            .filter(exam=exam)
            .select_related('section', 'paragraph')
            .order_by('section__order', 'order', 'id')
        )
        result = defaultdict(list)
        for q in qs:
            result[q.section_id].append({
                'id':           q.id,
                'global_num':   0,               # filled in below
                'text':         q.question_text,
                'options':      q.get_options(),
                'correct':      q.correct_option,
                'marks':        q.get_correct_marks(),
                'neg_marks':    q.get_negative_marks(),
                'order':        q.order,
                'paragraph_id': q.paragraph_id,
                'explanation':  q.explanation,
            })
        return dict(result)

    with ThreadPoolExecutor(max_workers=3) as pool:
        fs  = pool.submit(fetch_sections)
        fp  = pool.submit(fetch_paragraphs)
        fq  = pool.submit(fetch_questions)
        sections_result  = fs.result()
        paragraphs_result= fp.result()
        questions_result = fq.result()

    # ── Assemble + assign global question numbers ─────────────────────────────
    g_num   = 1
    built   = []

    for sec in sections_result:
        paras = paragraphs_result.get(sec.id, [])
        para_map = {p['id']: p for p in paras}
        qs    = questions_result.get(sec.id, [])

        for q in qs:
            q['global_num'] = g_num
            g_num += 1

        built.append({
            'id':            sec.id,
            'title':         sec.title,
            'description':   sec.description,
            'order':         sec.order,
            'correct_marks': sec.get_correct_marks(),
            'negative_marks':sec.get_negative_marks(),
            'has_negative':  sec.get_has_negative(),
            'paragraphs':    paras,
            'question_groups': _build_question_groups(qs, para_map),
            # flat list also kept for palette rendering
            'questions_flat': qs,
        })

    data = {'total_questions': g_num - 1, 'sections': built}
    cache.set(key, data, EXAM_CACHE_TTL)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Leaderboard  (cached)
# ─────────────────────────────────────────────────────────────────────────────

def get_leaderboard(exam, limit: int = 50) -> list:
    key  = _lb_key(exam.pk)
    data = cache.get(key)
    if data is None:
        from .models import ExamAttempt
        data = list(
            ExamAttempt.objects
            .filter(exam=exam, is_submitted=True)
            .select_related('student')
            .order_by('-score')[:limit]
        )
        cache.set(key, data, RESULT_CACHE_TTL)
    return data