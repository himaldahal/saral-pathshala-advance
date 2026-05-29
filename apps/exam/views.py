"""
exams/views.py
"""
from __future__ import annotations

import json
import threading
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Exam, ExamAttempt, Question, QuestionAttempt
from .utils import get_exam_data, invalidate_exam_cache, get_leaderboard


# ─────────────────────────────────────────────────────────────────────────────
# Exam List
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def exam_list(request):
    cache_key = f'exam_list_{request.user.pk}'
    exams = cache.get(cache_key)

    if exams is None:
        qs = Exam.objects.select_related('course').filter(is_active=True)
        if request.user.is_staff or request.user.is_superuser:
            exams = list(qs)
        else:
            exams = [e for e in qs if e.is_accessible(request.user)]
        cache.set(cache_key, exams, 60)

    # Group by course
    courses: dict = {}
    for exam in exams:
        courses.setdefault(exam.course, []).append(exam)

    return render(request, 'exams/exam_list.html', {
        'courses': courses,
        'now': timezone.now(),
        'is_staff': request.user.is_staff or request.user.is_superuser,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Exam Detail  (pre-start info page)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def exam_detail(request, slug):
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    is_staff = request.user.is_staff or request.user.is_superuser
    if not is_staff and not exam.is_accessible(request.user):
        messages.error(request, "This exam is not available yet.")
        return redirect('exams:exam_list')

    attempt = ExamAttempt.objects.filter(student=request.user, exam=exam).first()

    return render(request, 'exams/exam_detail.html', {
        'exam':             exam,
        'attempt':          attempt,
        'sections_count':   exam.sections.count(),
        'questions_count':  exam.questions.count(),
        'is_staff':         is_staff,
        'now':              timezone.now(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Start / Resume
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def start_exam(request, slug):
    exam = get_object_or_404(Exam, slug=slug, is_active=True)
    is_staff = request.user.is_staff or request.user.is_superuser

    if not is_staff and not exam.is_accessible(request.user):
        messages.error(request, "This exam is not accessible.")
        return redirect('exams:exam_list')

    attempt, created = ExamAttempt.objects.get_or_create(
        student=request.user, exam=exam
    )

    if attempt.is_submitted:
        messages.info(request, "You have already submitted this exam.")
        return redirect('exams:exam_result', slug=slug)

    return redirect('exams:exam_attempt', slug=slug)


# ─────────────────────────────────────────────────────────────────────────────
# Exam Attempt  (main exam UI)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def exam_attempt(request, slug):
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    attempt = ExamAttempt.objects.filter(student=request.user, exam=exam).first()
    if not attempt:
        return redirect('exams:start_exam', slug=slug)
    if attempt.is_submitted:
        return redirect('exams:exam_result', slug=slug)

    # ── Load structured data (cached) ─────────────────────────────────────────
    exam_data = get_exam_data(exam)

    # ── Previously-saved answers ───────────────────────────────────────────────
    answered = {
        str(qa.question_id): qa.selected_option
        for qa in attempt.question_attempts.all()
    }

    # ── Timer calculation ──────────────────────────────────────────────────────
    end_timestamp = None         # JS ms timestamp

    if exam.duration_minutes:
        personal_end = attempt.started_at + timedelta(minutes=exam.duration_minutes)
        if exam.end_date:
            actual_end = min(personal_end, exam.end_date)
        else:
            actual_end = personal_end
        end_timestamp = int(actual_end.timestamp() * 1000)
    elif exam.end_date:
        end_timestamp = int(exam.end_date.timestamp() * 1000)

    is_unlimited = end_timestamp is None

    return render(request, 'exams/exam_attempt.html', {
        'exam':          exam,
        'attempt':       attempt,
        'exam_data':     exam_data,
        'answered_json': json.dumps(answered),
        'end_timestamp': end_timestamp,
        'is_unlimited':  is_unlimited,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Save answer  (AJAX — called on every option click)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def save_answer(request, slug):
    try:
        body = json.loads(request.body)
        qid  = int(body['question_id'])
        opt  = body.get('selected_option') or None
    except (KeyError, ValueError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'msg': 'Bad payload'}, status=400)

    exam    = get_object_or_404(Exam, slug=slug)
    attempt = get_object_or_404(ExamAttempt, student=request.user, exam=exam)

    if attempt.is_submitted:
        return JsonResponse({'status': 'error', 'msg': 'Exam submitted'}, status=400)

    question = get_object_or_404(Question, pk=qid, exam=exam)

    QuestionAttempt.objects.update_or_create(
        exam_attempt=attempt,
        question=question,
        defaults={'selected_option': opt},
    )

    return JsonResponse({'status': 'ok'})


# ─────────────────────────────────────────────────────────────────────────────
# Submit exam
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def submit_exam(request, slug):
    exam    = get_object_or_404(Exam, slug=slug)
    attempt = get_object_or_404(ExamAttempt, student=request.user, exam=exam)

    if attempt.is_submitted:
        return JsonResponse({
            'status': 'already_submitted',
            'redirect': request.build_absolute_uri(f'/exams/{slug}/result/')
        })

    # ── Bulk-save answers from localStorage payload ───────────────────────────
    try:
        body    = json.loads(request.body)
        answers = body.get('answers', {})
    except (json.JSONDecodeError, AttributeError):
        answers = {}

    if answers:
        q_map = {str(q.pk): q for q in exam.questions.all()}
        with transaction.atomic():
            for qid_str, opt in answers.items():
                q = q_map.get(str(qid_str))
                if q:
                    QuestionAttempt.objects.update_or_create(
                        exam_attempt=attempt,
                        question=q,
                        defaults={'selected_option': opt or None},
                    )

    # ── Submit + score in background thread ───────────────────────────────────
    def _submit_and_score():
        attempt.submit()
        invalidate_exam_cache(exam.pk)
        cache.delete(f'exam_list_{request.user.pk}')

    t = threading.Thread(target=_submit_and_score, daemon=True)
    t.start()
    t.join(timeout=5)   # wait max 5 s so redirect works

    return JsonResponse({
        'status': 'ok',
        'redirect': request.build_absolute_uri(f'/exams/{slug}/result/')
    })


# ─────────────────────────────────────────────────────────────────────────────
# Result page
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def exam_result(request, slug):
    exam    = get_object_or_404(Exam, slug=slug)
    attempt = get_object_or_404(ExamAttempt, student=request.user, exam=exam)

    if not attempt.is_submitted:
        return redirect('exams:exam_attempt', slug=slug)

    is_staff     = request.user.is_staff or request.user.is_superuser
    show_results = is_staff or exam.is_results_visible()

    if not show_results:
        return render(request, 'exams/result_pending.html', {
            'exam': exam, 'attempt': attempt,
            'result_mode': exam.result_mode,
            'publish_time': exam.result_publish_time,
        })

    exam_data    = get_exam_data(exam)
    answered     = {
        qa.question_id: qa.selected_option
        for qa in attempt.question_attempts.select_related('question').all()
    }
    total_marks  = sum(
        q['marks']
        for s in exam_data['sections']
        for g in s['question_groups']
        for q in g['questions']
    )
    percentage   = round(attempt.score / total_marks * 100, 1) if total_marks else 0
    leaderboard  = get_leaderboard(exam)

    return render(request, 'exams/exam_result.html', {
        'exam':        exam,
        'attempt':     attempt,
        'exam_data':   exam_data,
        'answered':    answered,
        'total_marks': total_marks,
        'percentage':  percentage,
        'leaderboard': leaderboard,
        'is_staff':    is_staff,
    })


# ─────────────────────────────────────────────────────────────────────────────
# JSON template download
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def download_template(request):
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404

    template = {
        "_instructions": (
            "Fill this JSON and upload it to instantly set up an exam. "
            "You can give this to Gemini/GPT to populate. "
            "Remove '_instructions' before uploading."
        ),
        "course_title": "COURSE NAME (must already exist in admin)",
        "exam": {
            "title":               "Exam Title",
            "description":         "<p>Optional HTML description shown on exam detail page.</p>",
            "instructions":        "<p>Rules and instructions shown before the student starts.</p>",
            "start_date":          "2024-06-01T10:00:00",
            "end_date":            "2024-06-01T13:00:00",
            "duration_minutes":    180,
            "correct_marks":       1.0,
            "negative_marks":      0.25,
            "has_negative_marking":True,
            "result_mode":         "after_end",
            "result_publish_time": None,
            "make_public_after":   False,
        },
        "sections": [
            {
                "title":              "Section I — Physics",
                "description":        "",
                "order":              1,
                "override_scoring":   False,
                "correct_marks":      None,
                "negative_marks":     None,
                "has_negative_marking": None,
                "paragraphs": [
                    {
                        "title":   "Passage 1",
                        "content": "Read the following passage and answer Q1–Q2.\n<p>Passage text here. Supports $LaTeX$, <b>HTML</b>, <pre><code class=\"language-python\">print('hello')</code></pre></p>",
                        "order":   1,
                    }
                ],
                "questions": [
                    {
                        "question_text":    "What is Newton's second law? $F = ?$",
                        "option_one":       "ma",
                        "option_two":       "mv",
                        "option_three":     "mg",
                        "option_four":      "mc²",
                        "correct_option":   "1",
                        "marks":            1.0,
                        "use_custom_marks": False,
                        "paragraph_order":  1,
                        "order":            1,
                        "explanation":      "Newton's second law: $F = ma$.",
                    },
                    {
                        "question_text":    "A standalone question (no paragraph)",
                        "option_one":       "Option A",
                        "option_two":       "Option B",
                        "option_three":     "Option C",
                        "option_four":      "Option D",
                        "correct_option":   "2",
                        "marks":            1.0,
                        "use_custom_marks": False,
                        "paragraph_order":  None,
                        "order":            2,
                        "explanation":      "",
                    },
                ],
            },
            {
                "title":              "Section II — Chemistry (2-mark, IOE style)",
                "description":        "",
                "order":              2,
                "override_scoring":   True,
                "correct_marks":      2.0,
                "negative_marks":     0.2,
                "has_negative_marking": True,
                "paragraphs":         [],
                "questions": [
                    {
                        "question_text":    "What is the atomic number of Carbon?",
                        "option_one":       "6",
                        "option_two":       "12",
                        "option_three":     "14",
                        "option_four":      "8",
                        "correct_option":   "1",
                        "marks":            2.0,
                        "use_custom_marks": False,
                        "paragraph_order":  None,
                        "order":            1,
                        "explanation":      "Carbon has atomic number 6.",
                    }
                ],
            },
        ],
    }

    content  = json.dumps(template, indent=2, ensure_ascii=False)
    response = HttpResponse(content, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="exam_template.json"'
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Import exam (staff only)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def import_exam_page(request):
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404
    return render(request, 'exams/import_exam.html')


@login_required
@require_POST
def import_exam(request):
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404

    from .importers import import_exam_from_json

    data = None
    if 'json_file' in request.FILES:
        try:
            data = json.loads(request.FILES['json_file'].read().decode('utf-8'))
        except Exception as e:
            messages.error(request, f"Invalid JSON file: {e}")
            return redirect('exams:import_exam_page')
    elif request.POST.get('json_text'):
        try:
            data = json.loads(request.POST['json_text'])
        except json.JSONDecodeError as e:
            messages.error(request, f"Invalid JSON: {e}")
            return redirect('exams:import_exam_page')

    if not data:
        messages.error(request, "No JSON data provided.")
        return redirect('exams:import_exam_page')

    try:
        exam = import_exam_from_json(data)
        messages.success(
            request,
            f"✓ Exam '{exam.title}' imported — "
            f"{exam.sections.count()} sections, {exam.questions.count()} questions."
        )
        return redirect('exams:exam_detail', slug=exam.slug)
    except Exception as e:
        messages.error(request, f"Import failed: {e}")
        return redirect('exams:import_exam_page')