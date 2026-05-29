from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import Http404
from .models import Course, Lecture, Enrollment, LectureProgress, Subject


def course_list(request):
    courses = Course.objects.filter(is_active=True).prefetch_related('subjects')
    enrolled_ids = set()

    if request.user.is_authenticated:
        enrolled_ids = set(
            Enrollment.objects.filter(user=request.user)
            .values_list('course_id', flat=True)
        )

    courses_with_meta = []
    for course in courses:
        courses_with_meta.append({
            'course': course,
            'is_enrolled': course.pk in enrolled_ids,
            'total_lectures': course.total_lectures(),
            'total_subjects': course.total_subjects(),
            'first_lecture': course.get_first_lecture(),
        })

    return render(request, 'courses/course_list.html', {
        'courses_with_meta': courses_with_meta,
    })


@login_required
def lecture_detail(request, lecture_id):
    lecture = get_object_or_404(
        Lecture.objects.select_related('section__subject'),
        pk=lecture_id
    )

    # Resolve the course from subject
    course = lecture.section.subject.courses.first()
    if not course:
        raise Http404("No course found for this lecture.")

    # Access control: superuser OR enrolled
    is_enrolled = Enrollment.objects.filter(
        user=request.user, course=course
    ).exists()

    if not (request.user.is_superuser or is_enrolled):
        return redirect('course_list')

    # Build sidebar: subjects → sections → lectures for this course
    subjects = (
        Subject.objects
        .filter(courses=course, is_active=True)
        .prefetch_related('sections__lectures')
        .order_by('order', 'id')
    )

    # Track progress
    completed_ids = set(
        LectureProgress.objects.filter(
            user=request.user, completed=True
        ).values_list('lecture_id', flat=True)
    )

    # Mark current lecture as watched
    LectureProgress.objects.update_or_create(
        user=request.user,
        lecture=lecture,
        defaults={'completed': True}
    )

    next_lecture = lecture.get_next_lecture(course)
    prev_lecture = lecture.get_prev_lecture(course)

    return render(request, 'courses/lecture_detail.html', {
        'lecture': lecture,
        'course': course,
        'subjects': subjects,
        'completed_ids': completed_ids,
        'next_lecture': next_lecture,
        'prev_lecture': prev_lecture,
    })
    
@login_required
def dashboard(request):

    enrollments = (
        Enrollment.objects
        .filter(user=request.user)
        .select_related('course')
        .order_by('-enrolled_at')
    )

    enrollment_data = []

    total_courses = enrollments.count()
    total_subjects = 0
    total_lectures = 0
    completed_lectures = 0

    recent_progress = []

    for enrollment in enrollments:

        course = enrollment.course

        lectures = (
            Lecture.objects
            .filter(section__subject__courses=course)
            .distinct()
            .order_by(
                'section__subject__order',
                'section__order',
                'order',
                'id'
            )
        )

        lecture_count = lectures.count()

        completed_count = (
            LectureProgress.objects
            .filter(
                user=request.user,
                lecture__in=lectures,
                completed=True
            )
            .count()
        )

        next_lecture = (
            lectures.exclude(
                progress__user=request.user,
                progress__completed=True
            )
            .first()
        )

        progress_percent = 0

        if lecture_count > 0:
            progress_percent = round(
                (completed_count / lecture_count) * 100
            )

        enrollment_data.append({
            'enrollment': enrollment,
            'course': course,
            'lecture_count': lecture_count,
            'completed_count': completed_count,
            'progress_percent': progress_percent,
            'subject_count': course.total_subjects(),
            'next_lecture': next_lecture,
        })

        total_subjects += course.total_subjects()
        total_lectures += lecture_count
        completed_lectures += completed_count

    overall_progress = 0

    if total_lectures > 0:
        overall_progress = round(
            (completed_lectures / total_lectures) * 100
        )

    # ONLY recent activity from enrolled courses
    enrolled_course_lectures = Lecture.objects.filter(
        section__subject__courses__in=[
            enrollment.course for enrollment in enrollments
        ]
    ).distinct()

    recent_progress = (
        LectureProgress.objects
        .filter(
            user=request.user,
            lecture__in=enrolled_course_lectures
        )
        .select_related(
            'lecture',
            'lecture__section',
            'lecture__section__subject'
        )
        .order_by('-watched_at')[:5]
    )

    context = {
        'user': request.user,

        'enrollments': enrollments,
        'enrollment_data': enrollment_data,

        'total_courses': total_courses,
        'total_subjects': total_subjects,
        'total_lectures': total_lectures,
        'completed_lectures': completed_lectures,
        'overall_progress': overall_progress,

        'recent_progress': recent_progress,
    }

    return render(request, 'dashboard.html', context)