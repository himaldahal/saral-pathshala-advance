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
from django.urls import reverse

from .models import Exam, ExamAttempt, Question, QuestionAttempt
from .utils import get_exam_data, invalidate_exam_cache, get_leaderboard
from apps.pages.models import Course


# ─────────────────────────────────────────────────────────────────────────────
# Exam List
# ─────────────────────────────────────────────────────────────────────────────

def exam_list(request):
    is_auth = request.user.is_authenticated
    is_staff = is_auth and (request.user.is_staff or request.user.is_superuser)
    
    qs = Exam.objects.select_related('course').filter(is_active=True)
    if is_staff:
        exams = list(qs)
    else:
        exams = [e for e in qs if e.is_accessible(request.user if is_auth else None)]

    interested_course = None
    interested_exams = []
    other_exams = []
    attempts = {}

    if is_auth:
        attempts = {
            att.exam_id: att
            for att in ExamAttempt.objects.filter(student=request.user)
        }
        interested_course = request.user.interested_course

    for exam in exams:
        exam.user_attempt = attempts.get(exam.id)
        # Fetch total marks for display on result/retake badges
        exam.total_marks_val = exam.total_marks()
        if exam.user_attempt:
            # Calculate accuracy percentage score
            total = exam.total_marks_val
            score = exam.user_attempt.score
            exam.user_attempt.percentage = round((score / total) * 100, 1) if total > 0 else 0.0

    if interested_course:
        for exam in exams:
            if exam.course == interested_course:
                interested_exams.append(exam)
            else:
                other_exams.append(exam)
    else:
        other_exams = exams

    return render(request, 'exams/exam_list.html', {
        'interested_course': interested_course,
        'interested_exams': interested_exams,
        'other_exams': other_exams,
        'now': timezone.now(),
        'is_staff': is_staff,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Exam Detail  (pre-start info page)
# ─────────────────────────────────────────────────────────────────────────────

def exam_detail(request, slug):
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    is_staff = request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)
    if not is_staff and not exam.is_accessible(request.user if request.user.is_authenticated else None):
        messages.error(request, "This exam is not available yet.")
        return redirect('exams:exam_list')

    attempt = None
    if request.user.is_authenticated:
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

    # Preserve fresh parameter if present
    redirect_url = reverse('exams:exam_attempt', kwargs={'slug': slug})
    if request.GET.get('fresh') == '1':
        redirect_url += "?fresh=1"
    return redirect(redirect_url)


# ─────────────────────────────────────────────────────────────────────────────
# Exam Attempt  (main exam UI)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def exam_attempt(request, slug):
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    attempt = ExamAttempt.objects.filter(student=request.user, exam=exam).first()
    if not attempt:
        return redirect('exams:start_exam', slug=slug)

    # ── Expiry + auto-submit logic ────────────────────────────────────────────
    # Determines whether the exam window has closed for this student.
    # If make_public_after is True the exam is still accessible after end_date,
    # so we must NOT auto-submit — we just flag it as expired for the template.
    is_expired = False

    if not attempt.is_submitted:
        now = timezone.now()

        if exam.duration_minutes:
            personal_end = attempt.started_at + timedelta(minutes=exam.duration_minutes)
            actual_end   = min(personal_end, exam.end_date) if exam.end_date else personal_end
            timed_out    = now > actual_end
        else:
            timed_out = bool(exam.end_date) and now > exam.end_date

        if timed_out:
            if exam.make_public_after:
                # Exam is past its window but still publicly accessible —
                # do NOT auto-submit; let the student finish and submit manually.
                is_expired = True
            else:
                # Normal expiry — auto-submit and redirect to results.
                attempt.submit()
                invalidate_exam_cache(exam.pk)
                cache.delete(f'exam_list_{request.user.pk}')
                messages.info(
                    request,
                    "The exam duration has expired. "
                    "Your attempt has been automatically submitted and scored."
                )
                return redirect('exams:exam_result', slug=slug)

    if attempt.is_submitted:
        return redirect('exams:exam_result', slug=slug)

    # ── Load structured data (cached) ────────────────────────────────────────
    exam_data = get_exam_data(exam)

    # ── Strip answers and explanations to prevent leakage ────────────────────
    import copy
    clean_data = copy.deepcopy(exam_data)
    for sec in clean_data.get('sections', []):
        for group in sec.get('question_groups', []):
            for q in group.get('questions', []):
                q.pop('correct', None)
                q.pop('explanation', None)
        for q in sec.get('questions_flat', []):
            q.pop('correct', None)
            q.pop('explanation', None)
    exam_data = clean_data

    # ── Previously-saved answers ──────────────────────────────────────────────
    answered = {
        str(qa.question_id): qa.selected_option
        for qa in attempt.question_attempts.all()
    }

    # ── Timer calculation ─────────────────────────────────────────────────────
    # end_timestamp is a JS-compatible ms timestamp used by the countdown timer.
    # For expired-but-public exams we still pass the (past) timestamp so the
    # template can render "00:00:00", but IS_EXPIRED in JS prevents auto-submit.
    end_timestamp = None

    if exam.duration_minutes:
        personal_end = attempt.started_at + timedelta(minutes=exam.duration_minutes)
        actual_end   = min(personal_end, exam.end_date) if exam.end_date else personal_end
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
        'is_expired':    is_expired,   # True only for make_public_after past-deadline exams
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
        if request.content_type == 'application/json':
            return JsonResponse({
                'status': 'already_submitted',
                'redirect': request.build_absolute_uri(f'/exams/{slug}/result/')
            })
        else:
            return redirect('exams:exam_result', slug=slug)

    # ── Bulk-save answers from localStorage payload / form payload ───────────────────
    answers = {}
    is_json = request.content_type == 'application/json'
    
    if is_json:
        try:
            body    = json.loads(request.body)
            answers = body.get('answers', {})
        except (json.JSONDecodeError, AttributeError):
            pass
    else:
        try:
            answers_raw = request.POST.get('answers_json', '{}')
            answers = json.loads(answers_raw)
        except (json.JSONDecodeError, AttributeError):
            pass

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

    if is_json:
        return JsonResponse({
            'status': 'ok',
            'redirect': request.build_absolute_uri(f'/exams/{slug}/result/')
        })
    else:
        messages.success(request, "Your exam has been submitted and scored successfully!")
        return redirect('exams:exam_result', slug=slug)


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
    
    total_marks = 0
    for s in exam_data.get('sections', []):
        for g in s.get('question_groups', []):
            for q in g.get('questions', []):
                total_marks += q.get('marks', 0)
        for q in s.get('questions_flat', []):
            total_marks += q.get('marks', 0)
            
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

    # Build available courses list for reference
    courses = list(
        Course.objects.filter(is_active=True).values('slug', 'name').order_by('name')
    )
    courses_ref = {c['slug']: c['name'] for c in courses}
    first_slug = courses[0]['slug'] if courses else 'your-course-slug-here'

    template = {
        "_instructions": (
            "1. Replace 'course_slug' with one of the slugs listed in '_available_courses'.\n"
            "2. Fill in the exam details and sections.\n"
            "3. Give this file to Gemini/GPT to populate questions automatically.\n"
            "4. Remove '_instructions' and '_available_courses' before uploading.\n"
            "5. Dates must be ISO-8601 format: YYYY-MM-DDTHH:MM:SS"
        ),
        "_available_courses": courses_ref,

        # ── Top-level ──────────────────────────────────────────────────────
        "course_slug": first_slug,

        # ── Exam meta ──────────────────────────────────────────────────────
        "exam": {
            "title":               "Exam Title Here",
            "description":         "<p>Optional HTML description shown on the exam detail page.</p>",
            "instructions":        "<p>Rules and instructions shown to the student before they start.</p>",

            # Scheduling
            "start_date":          "2024-06-01T10:00:00",
            "end_date":            "2024-06-01T13:00:00",   # null = no deadline
            "duration_minutes":    180,                      # null = unlimited

            # Scoring defaults (can be overridden per-section or per-question)
            "correct_marks":        1.0,
            "negative_marks":       0.25,
            "has_negative_marking": True,

            # Visibility
            "make_public":          False,   # True = always open (practice exam)
            "make_public_after":    False,   # True = allow attempts after end_date
            "is_active":            True,

            # Results
            # Options: "hidden" | "after_end" | "auto" | "manual"
            "result_mode":          "after_end",
            "result_publish_time":  None,    # Only used when result_mode = "auto"
        },

        # ── Sections ───────────────────────────────────────────────────────
        "sections": [
            {
                "title":       "Section I — Physics",
                "description": "",
                "order":       1,

                # Set override_scoring=true to use custom marks for this section
                # instead of the exam-level defaults above.
                "override_scoring":    False,
                "correct_marks":       None,
                "negative_marks":      None,
                "has_negative_marking": None,

                # ── Paragraphs (optional reading passages) ─────────────────
                # Leave as [] if no passages are needed.
                # Questions link to a paragraph via paragraph_order.
                "paragraphs": [
                    {
                        "title":   "Passage 1",
                        "content": (
                            "Read the following passage and answer Q1–Q2.\n"
                            "<p>Passage text here. Supports $LaTeX$ inline math, "
                            "<b>HTML</b>, and code blocks: "
                            "<pre><code class=\"language-python\">print('hello')</code></pre></p>"
                        ),
                        "order": 1,
                    }
                ],

                # ── Questions ──────────────────────────────────────────────
                "questions": [
                    {
                        "order":            1,
                        "question_text":    "What is Newton's second law? $F = ?$",
                        "option_one":       "$ma$",
                        "option_two":       "$mv$",
                        "option_three":     "$mg$",
                        "option_four":      "$mc^2$",
                        "correct_option":   "1",         # "1" | "2" | "3" | "4"
                        "explanation":      "Newton's second law: $F = ma$.",
                        "paragraph_order":  1,           # links to paragraph above; null if standalone
                        "marks":            1.0,
                        "use_custom_marks": False,       # True = use this question's marks value
                    },
                    {
                        "order":            2,
                        "question_text":    "A standalone question with no reading passage.",
                        "option_one":       "Option A",
                        "option_two":       "Option B",
                        "option_three":     "Option C",
                        "option_four":      "Option D",
                        "correct_option":   "2",
                        "explanation":      "",
                        "paragraph_order":  None,
                        "marks":            1.0,
                        "use_custom_marks": False,
                    },
                ],
            },

            {
                "title":       "Section II — Chemistry (IOE-style 2-mark section)",
                "description": "",
                "order":       2,

                # This section overrides exam-level scoring
                "override_scoring":    True,
                "correct_marks":       2.0,
                "negative_marks":      0.2,
                "has_negative_marking": True,

                "paragraphs": [],

                "questions": [
                    {
                        "order":            1,
                        "question_text":    "What is the atomic number of Carbon?",
                        "option_one":       "6",
                        "option_two":       "12",
                        "option_three":     "14",
                        "option_four":      "8",
                        "correct_option":   "1",
                        "explanation":      "Carbon has atomic number 6 and mass number 12.",
                        "paragraph_order":  None,
                        "marks":            2.0,
                        "use_custom_marks": False,
                    },
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


@login_required
def delete_attempt(request, slug):
    """Deletes a student's own exam attempt, allowing them to retake the exam."""
    exam = get_object_or_404(Exam, slug=slug)
    attempt = get_object_or_404(ExamAttempt, student=request.user, exam=exam)
    
    # Cascade delete is handled by Django models automatically (exam_attempt -> question_attempts)
    attempt.delete()
    
    # Invalidate Cache
    cache.delete(f'exam_list_{request.user.pk}')
    
    messages.success(request, f"Your previous attempt for '{exam.title}' has been cleared successfully. Starting a fresh retake!")
    
    # Redirect directly to start_exam with fresh=1 to trigger fresh attempt clean-slate
    return redirect(reverse('exams:start_exam', kwargs={'slug': slug}) + "?fresh=1")