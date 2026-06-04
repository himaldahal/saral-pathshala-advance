from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.core.cache import cache
from django.urls import reverse
from django.conf import settings

from .models import Course, Lecture, Enrollment, LectureProgress, Subject, Notice, CourseEnrollmentRequest, SiteSetting
from apps.cauth.models import User, StudentLevel
from apps.exam.models import Exam, ExamAttempt

# =========================================================
# HOMEPAGE & STATIC PAGES
# =========================================================

def home(request):
    """SEO-focused, content-rich homepage for Saral Pathshala. Query-cached."""
    cached_home = cache.get('homepage_data')
    if not cached_home:
        courses = list(Course.objects.filter(is_active=True).prefetch_related('subjects')[:6])
        upcoming_exams = list(Exam.objects.filter(
            is_active=True,
            start_date__gte=timezone.now()
        ).order_by('start_date')[:6])
        notices = list(Notice.objects.filter(is_active=True).order_by('-created_at')[:6])
        
        cached_home = {
            'courses': courses,
            'upcoming_exams': upcoming_exams,
            'notices': notices
        }
        cache.set('homepage_data', cached_home, 300) # Cache for 5 mins
        
    return render(request, 'home.html', {
        'courses': cached_home['courses'],
        'upcoming_exams': cached_home['upcoming_exams'],
        'notices': cached_home['notices'],
        'now': timezone.now(),
    })

def about(request):
    """About Us page."""
    return render(request, 'about.html')

def contact(request):
    """Contact Us page with dynamic course lead dropdown options."""
    courses = cache.get('contact_courses_all')
    if not courses:
        courses = list(Course.objects.filter(is_active=True))
        cache.set('contact_courses_all', courses, 600)
    return render(request, 'contact.html', {'courses': courses})


# =========================================================
# COURSE VIEWS
# =========================================================

def course_list(request):
    courses = cache.get('course_list_all')
    if not courses:
        courses = list(Course.objects.filter(is_active=True).prefetch_related('subjects'))
        cache.set('course_list_all', courses, 600)

    enrolled_ids = set()
    if request.user.is_authenticated:
        enrolled_ids = set(
            Enrollment.objects.filter(user=request.user)
            .values_list('course_id', flat=True)
        )

    courses_with_meta = []
    for course in courses:
        total_lectures_key = f'course_total_lectures_{course.slug}'
        total_lectures = cache.get(total_lectures_key)
        if total_lectures is None:
            total_lectures = course.total_lectures()
            cache.set(total_lectures_key, total_lectures, 600)

        total_subjects_key = f'course_total_subjects_{course.slug}'
        total_subjects = cache.get(total_subjects_key)
        if total_subjects is None:
            total_subjects = course.total_subjects()
            cache.set(total_subjects_key, total_subjects, 600)

        first_lecture_key = f'course_first_lecture_{course.slug}'
        first_lecture = cache.get(first_lecture_key)
        if first_lecture is None:
            first_lecture = course.get_first_lecture()
            cache.set(first_lecture_key, first_lecture, 600)

        courses_with_meta.append({
            'course': course,
            'is_enrolled': (course.pk in enrolled_ids) or (request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff)),
            'total_lectures': total_lectures,
            'total_subjects': total_subjects,
            'first_lecture': first_lecture,
        })

    return render(request, 'courses/course_list.html', {
        'courses_with_meta': courses_with_meta,
    })


def course_detail(request, slug):
    """SEO detail page for a course displaying subjects, sections, syllabus. Cached."""
    course_key = f'course_detail_obj_{slug}'
    course = cache.get(course_key)
    if not course:
        course = get_object_or_404(Course, slug=slug, is_active=True)
        cache.set(course_key, course, 600)

    subjects_key = f'course_subjects_{slug}'
    subjects = cache.get(subjects_key)
    if not subjects:
        subjects = list(course.subjects.filter(is_active=True).prefetch_related('sections__lectures').order_by('order', 'id'))
        cache.set(subjects_key, subjects, 600)
    
    is_enrolled = False
    if request.user.is_authenticated:
        is_enrolled = request.user.is_superuser or request.user.is_staff or Enrollment.objects.filter(user=request.user, course=course).exists()
        
    return render(request, 'courses/course_detail.html', {
        'course': course,
        'subjects': subjects,
        'is_enrolled': is_enrolled,
    })


@login_required
def enroll_instantly(request, slug):
    """Creates a CourseEnrollmentRequest lead instead of instant enrollment."""
    course = get_object_or_404(Course, slug=slug, is_active=True)
    
    # Check if request already exists
    already_requested = CourseEnrollmentRequest.objects.filter(
        email=request.user.email,
        course=course
    ).exists()
    
    if not already_requested:
        CourseEnrollmentRequest.objects.create(
            name=request.user.full_name or request.user.email,
            phone=request.user.phone or "0000000000",
            email=request.user.email,
            course=course,
            message="Auto-generated request from logged-in student.",
            status='pending'
        )
    messages.success(request, f"Your enrollment request for '{course.name}' has been submitted successfully. A staff member will contact you soon!")
    return redirect('course_detail', slug=slug)


def enroll_request(request):
    """Guest enrollment request form. Protected by honeypot and rate-limiting."""
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        course_slug = request.POST.get('course_slug', '').strip()
        message = request.POST.get('message', '').strip()
        
        # Honeypot field check
        honeypot = request.POST.get('website_url', '').strip()
        if honeypot:
            messages.success(request, "Enrollment request submitted successfully.")
            return redirect('course_list')

        course = get_object_or_404(Course, slug=course_slug)
        
        if not name or not phone:
            messages.error(request, "Full name and Phone number are required.")
            return redirect('course_detail', slug=course_slug)

        # Enforce Nepalese phone basic validation matching registration
        import re
        if not re.match(r'^(97|98)\d{8}$', phone):
            messages.error(request, "Please enter a valid Nepalese phone number starting with 97 or 98 (10 digits).")
            return redirect('course_detail', slug=course_slug)

        # Lead submission rate-limiting: 30 minutes block
        cache_key = f"enroll_lead_{phone}_{course.pk}"
        if cache.get(cache_key):
            messages.warning(request, "We have already received an enrollment request from this number recently. We will contact you soon.")
            return redirect('course_detail', slug=course_slug)

        # IP-based rate-limiting to prevent lead flooding
        from apps.cauth.utils import get_client_ip
        ip_address = get_client_ip(request)
        ip_lead_key = f"enroll_lead_ip_{ip_address}"
        ip_lead_attempts = cache.get(ip_lead_key, 0)
        if ip_lead_attempts >= 5:
            messages.error(request, "Too many enrollment requests from your device. Please try again later.")
            return redirect('course_detail', slug=course_slug)

        CourseEnrollmentRequest.objects.create(
            name=name,
            phone=phone,
            email=email,
            course=course,
            message=message
        )
        cache.set(cache_key, True, 1800) # 30 min lock
        cache.set(ip_lead_key, ip_lead_attempts + 1, 3600) # 1 hour block for IP

        messages.success(request, "Thank you! Your enrollment request has been submitted. Our team will call you shortly.")
        return redirect('course_detail', slug=course_slug)
        
    return redirect('course_list')


# =========================================================
# LECTURE VIEWS
# =========================================================

def lecture_detail(request, lecture_id):
    lecture = get_object_or_404(
        Lecture.objects.select_related('section__subject'),
        pk=lecture_id
    )

    # Resolve the course from subject
    course = lecture.section.subject.courses.first()
    if not course:
        raise Http404("No course found for this lecture.")

    # Access control: force login to view any content.
    if not request.user.is_authenticated:
        messages.warning(request, "Please log in to view this lecture.")
        return redirect('login')

    # Non-preview lectures require enrollment (or staff/superuser).
    if not lecture.is_preview:
        is_enrolled = Enrollment.objects.filter(
            user=request.user, course=course
        ).exists()

        if not (request.user.is_superuser or request.user.is_staff or is_enrolled):
            messages.error(request, "You must be enrolled in this course to view this lecture.")
            return redirect('course_detail', slug=course.slug)

    # Build sidebar: subjects → sections → lectures for this course
    subjects = (
        Subject.objects
        .filter(courses=course, is_active=True)
        .prefetch_related('sections__lectures')
        .order_by('order', 'id')
    )

    # Track progress (authenticated users only)
    completed_ids = set()
    if request.user.is_authenticated:
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

    is_enrolled = False
    if request.user.is_authenticated:
        is_enrolled = Enrollment.objects.filter(
            user=request.user, course=course
        ).exists() or request.user.is_superuser or request.user.is_staff

    next_lecture = lecture.get_next_lecture(course)
    prev_lecture = lecture.get_prev_lecture(course)

    return render(request, 'courses/lecture_detail.html', {
        'lecture': lecture,
        'course': course,
        'subjects': subjects,
        'completed_ids': completed_ids,
        'next_lecture': next_lecture,
        'prev_lecture': prev_lecture,
        'is_enrolled': is_enrolled,
    })


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@login_required
def dashboard(request):
    # Enforce profile updates
    if request.method == "POST":
        if "update_profile" in request.POST:
            full_name = request.POST.get('full_name', '').strip()
            previous_institute = request.POST.get('previous_institute', '').strip()
            current_level = request.POST.get('current_level', '').strip()
            interested_course_slug = request.POST.get('interested_course', '').strip()
            
            if not full_name:
                messages.error(request, "Full name cannot be empty.")
                return redirect('dashboard')
                
            # Update profile info (except phone and date_joined)
            request.user.full_name = full_name
            request.user.previous_institute = previous_institute
            
            if current_level in [choice[0] for choice in StudentLevel.choices]:
                request.user.current_level = current_level
            elif not current_level:
                request.user.current_level = None
                
            if interested_course_slug:
                interested_course = Course.objects.filter(slug=interested_course_slug, is_active=True).first()
                request.user.interested_course = interested_course
            else:
                request.user.interested_course = None
                
            # Email Update logic (allowed ONLY if unverified)
            if not request.user.is_email_verified:
                email = request.POST.get('email', '').strip().lower()
                if email:
                    if email != request.user.email:
                        if User.objects.exclude(pk=request.user.pk).filter(email=email).exists():
                            messages.error(request, "This email is already registered to another account.")
                        else:
                            request.user.email = email
                            messages.info(request, "Your email has been updated. Please verify it to secure your account.")
                else:
                    messages.error(request, "Email address cannot be empty.")
                    return redirect('dashboard')
            
            request.user.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('dashboard')
            
        elif "request_verification" in request.POST:
            # Prevent abuse using the built-in rate-limiting system
            from apps.cauth.utils import generate_and_dispatch_email_token
            success, msg = generate_and_dispatch_email_token(request.user, request)
            if success:
                messages.success(request, "Verification link sent! Please check your email inbox.")
            else:
                messages.warning(request, msg)
            return redirect('dashboard')

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

    # ── Exam Performance Analytics Chart ──────────────────────────────────────
    from django.db.models import Avg
    import json
    
    attempts = ExamAttempt.objects.filter(
        student=request.user, 
        is_submitted=True
    ).select_related('exam').order_by('completed_at')

    chart_labels = []
    chart_scores = []
    chart_averages = []

    for att in attempts:
        chart_labels.append(att.exam.title)
        total_marks = att.exam.total_marks()
        
        # Student score percentage
        score_pct = round((att.score / total_marks) * 100, 1) if total_marks > 0 else 0.0
        chart_scores.append(score_pct)
        
        # Global class average percentage for this exam
        avg_score_agg = ExamAttempt.objects.filter(
            exam=att.exam, 
            is_submitted=True
        ).aggregate(avg=Avg('score'))
        
        avg_score = avg_score_agg['avg'] or 0.0
        avg_pct = round((avg_score / total_marks) * 100, 1) if total_marks > 0 else 0.0
        chart_averages.append(avg_pct)

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
        'chart_labels_json': json.dumps(chart_labels),
        'chart_scores_json': json.dumps(chart_scores),
        'chart_averages_json': json.dumps(chart_averages),
        'has_attempts': attempts.exists(),
        'attempts': attempts,
        'active_courses': Course.objects.filter(is_active=True).order_by('name'),
        'student_levels': StudentLevel.choices,
    }

    return render(request, 'dashboard.html', context)


# =========================================================
# NOTICES (PHYSICAL EXAMS & RESULTS)
# =========================================================

def notice_list(request):
    """SEO optimized list of notices."""
    notices = Notice.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'notices/notice_list.html', {'notices': notices})


def notice_detail(request, slug):
    """SEO optimized detail view of a notice with PDF rendering."""
    notice = get_object_or_404(Notice, slug=slug, is_active=True)
    return render(request, 'notices/notice_detail.html', {'notice': notice})


# =========================================================
# DYNAMIC CACHED SITEMAP
# =========================================================

def sitemap_xml(request):
    """
    Generates a dynamic XML sitemap of all active urls.
    Cached for 6 hours to minimize DB hits.
    """
    sitemap_data = cache.get('sitemap_xml_data')
    if not sitemap_data:
        host = f"https://{request.get_host()}"
        urls = [
            f"{host}/",
            f"{host}/courses/",
            f"{host}/notices/",
            f"{host}/exams/",
        ]
        
        # Course Detail URLs
        for course in Course.objects.filter(is_active=True):
            urls.append(f"{host}{course.get_absolute_url()}")
            
        # Notice Detail URLs
        for notice in Notice.objects.filter(is_active=True):
            urls.append(f"{host}{notice.get_absolute_url()}")
            
        # Exam Detail URLs
        for exam in Exam.objects.filter(is_active=True):
            urls.append(f"{host}{reverse('exams:exam_detail', kwargs={'slug': exam.slug})}")
            
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for url in urls:
            xml += f'  <url>\n    <loc>{url}</loc>\n    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
        xml += '</urlset>'
        sitemap_data = xml
        cache.set('sitemap_xml_data', sitemap_data, 21600) # 6 hours cache
        
    return HttpResponse(sitemap_data, content_type='application/xml')


def robots_txt(request):
    host = f"https://{request.get_host()}"

    content = f"""User-agent: *\nAllow: /\nSitemap: {host}/sitemap.xml
                """

    return HttpResponse(content, content_type="text/plain")

def handler404(request, exception=None):
    """Custom 404 Page Not Found error handler."""
    return render(request, '404.html', status=404)


def handler500(request):
    """Custom 500 Internal Server Error handler."""
    return render(request, '500.html', status=500)


# =========================================================
# STAFF & ADMIN CUSTOM UTILITIES
# =========================================================

@login_required
def admin_import_enrollments(request):
    """
    Staff / Superuser utility to import user enrollments in bulk via CSV or JSON.
    Tracks enrolled_by and enrolled_at.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404("You do not have permission to view this page.")

    import csv
    import json

    results = None
    if request.method == "POST":
        file_type = request.POST.get('file_type')
        uploaded_file = request.FILES.get('import_file')
        
        if not uploaded_file:
            messages.error(request, "Please upload a CSV or JSON file.")
            return redirect('admin_import_enrollments')

        # Read the file content
        try:
            content = uploaded_file.read().decode('utf-8')
        except Exception as e:
            messages.error(request, f"Error reading file: {e}")
            return redirect('admin_import_enrollments')

        records = []
        errors = []
        success_count = 0

        # Parse CSV or JSON
        if file_type == 'csv' or uploaded_file.name.endswith('.csv'):
            reader = csv.DictReader(content.splitlines())
            for row_idx, row in enumerate(reader, 1):
                course_slug = row.get('course-slug') or row.get('course_slug')
                email = row.get('email')
                phone = row.get('phone') or row.get('phone_no') or row.get('phone-no')
                
                if not course_slug:
                    errors.append(f"Row {row_idx}: Missing course-slug.")
                    continue
                if not email and not phone:
                    errors.append(f"Row {row_idx}: Both email and phone are missing.")
                    continue
                records.append({
                    'course_slug': course_slug.strip(),
                    'email': email.strip() if email else None,
                    'phone': phone.strip() if phone else None,
                    'row_num': row_idx
                })
        else: # JSON
            try:
                data = json.loads(content)
                if not isinstance(data, list):
                    messages.error(request, "JSON content must be a list of objects.")
                    return redirect('admin_import_enrollments')
                for idx, item in enumerate(data, 1):
                    course_slug = item.get('course-slug') or item.get('course_slug')
                    email = item.get('email')
                    phone = item.get('phone') or item.get('phone_no') or item.get('phone-no')
                    
                    if not course_slug:
                        errors.append(f"Item {idx}: Missing course-slug.")
                        continue
                    if not email and not phone:
                        errors.append(f"Item {idx}: Both email and phone are missing.")
                        continue
                    records.append({
                        'course_slug': str(course_slug).strip(),
                        'email': str(email).strip() if email else None,
                        'phone': str(phone).strip() if phone else None,
                        'row_num': idx
                    })
            except Exception as e:
                messages.error(request, f"Invalid JSON payload: {e}")
                return redirect('admin_import_enrollments')

        # Process the records
        from django.db import transaction
        for rec in records:
            course = Course.objects.filter(slug=rec['course_slug']).first()
            if not course:
                errors.append(f"Row/Item {rec['row_num']}: Course with slug '{rec['course_slug']}' not found.")
                continue

            user = None
            # Give precedence to email
            if rec['email']:
                user = User.objects.filter(email=rec['email']).first()
            if not user and rec['phone']:
                user = User.objects.filter(phone=rec['phone']).first()

            if not user:
                errors.append(f"Row/Item {rec['row_num']}: User not found with email '{rec['email']}' or phone '{rec['phone']}'.")
                continue

            # Create enrollment
            with transaction.atomic():
                enrollment, created = Enrollment.objects.get_or_create(
                    user=user,
                    course=course,
                    defaults={
                        'enrolled_by': request.user
                    }
                )
                if created:
                    success_count += 1
                else:
                    errors.append(f"Row/Item {rec['row_num']}: Student {user.email} is already enrolled in {course.name}.")

        results = {
            'success_count': success_count,
            'errors': errors,
            'total_processed': len(records)
        }
        if success_count > 0:
            messages.success(request, f"Import complete! Enrolled {success_count} students successfully.")
        if errors:
            messages.warning(request, f"Import completed with {len(errors)} warnings/errors.")

    return render(request, 'admin_custom/import_enrollments.html', {
        'results': results
    })


@login_required
def admin_dashboard(request):
    """
    Highly customized, feature-rich admin dashboard.
    Shows real-time exam takers, scores, distributions, enrollment leads CRM, and demographics.
    Also serves as a system operations command center, supporting background queue manual flushing,
    diagnostics, student account status controls, and exam attempt clears.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404("You do not have permission to view this page.")

    from django.db.models import Avg, Max, Min
    import json
    from datetime import timedelta
    from django.core.management import call_command
    from django.core.mail import send_mail
    from apps.cauth.models import MailQueue, SMSQueue, QueueStatus
    
    # Handle Administrative Action POSTs
    if request.method == "POST":
        # 1) Portal Settings Update
        if "update_settings" in request.POST:
            site_settings = SiteSetting.objects.first()
            if not site_settings:
                site_settings = SiteSetting.objects.create()
                
            site_settings.site_name = request.POST.get('site_name', '').strip()
            site_settings.site_title = request.POST.get('site_title', '').strip()
            site_settings.site_description = request.POST.get('site_description', '').strip()
            site_settings.meta_keywords = request.POST.get('meta_keywords', '').strip()
            
            site_settings.contact_email = request.POST.get('contact_email', '').strip()
            site_settings.contact_phone = request.POST.get('contact_phone', '').strip()
            site_settings.contact_address = request.POST.get('contact_address', '').strip()
            site_settings.whatsapp_number = request.POST.get('whatsapp_number', '').strip()
            
            site_settings.social_facebook = request.POST.get('social_facebook', '').strip()
            site_settings.social_twitter = request.POST.get('social_twitter', '').strip()
            site_settings.social_instagram = request.POST.get('social_instagram', '').strip()
            site_settings.social_tiktok = request.POST.get('social_tiktok', '').strip()
            site_settings.social_linkedin = request.POST.get('social_linkedin', '').strip()
            site_settings.social_threads = request.POST.get('social_threads', '').strip()
            
            site_settings.google_analytics_id = request.POST.get('google_analytics_id', '').strip()
            
            if 'logo' in request.FILES:
                site_settings.logo = request.FILES['logo']
            if 'favicon' in request.FILES:
                site_settings.favicon = request.FILES['favicon']
                
            site_settings.save()
            messages.success(request, "Portal settings updated successfully!")
            return redirect('admin_dashboard')
            
        # 2) Process/Flush Mail Queue
        elif "process_mail_queue" in request.POST:
            try:
                call_command('process_mail_queue')
                messages.success(request, "Mail Queue processed successfully! Pending emails have been sent.")
            except Exception as e:
                messages.error(request, f"Failed to process Mail Queue: {str(e)}")
            return redirect('admin_dashboard')
            
        # 3) Process/Flush SMS Queue
        elif "process_sms_queue" in request.POST:
            try:
                call_command('process_sms_queue')
                messages.success(request, "SMS Queue processed successfully! Pending SMS messages have been sent.")
            except Exception as e:
                messages.error(request, f"Failed to process SMS Queue: {str(e)}")
            return redirect('admin_dashboard')
            
        # 3.5) Run Unified Cron Task
        elif "run_unified_cron" in request.POST:
            try:
                call_command('unified_cron')
                messages.success(request, "Unified Cron Task completed successfully! Dispatched pending OTPs, reset emails, and cleared old/used tokens.")
            except Exception as e:
                messages.error(request, f"Failed to run Unified Cron: {str(e)}")
            return redirect('admin_dashboard')
            
        # 4) Retry Failed Queues
        elif "retry_failed_queues" in request.POST:
            mail_count = MailQueue.objects.filter(status=QueueStatus.FAILED).update(status=QueueStatus.PENDING, retry_count=0)
            sms_count = SMSQueue.objects.filter(status=QueueStatus.FAILED).update(status=QueueStatus.PENDING, retry_count=0)
            messages.success(request, f"Successfully reset retry counters! Queued {mail_count} failed emails and {sms_count} failed SMS back to PENDING.")
            return redirect('admin_dashboard')

        # 5) Delete a specific student attempt (reset mock exams)
        elif "delete_student_attempt" in request.POST:
            attempt_id = request.POST.get('attempt_id', '').strip()
            attempt_to_delete = get_object_or_404(ExamAttempt, pk=attempt_id)
            student = attempt_to_delete.student
            exam_title = attempt_to_delete.exam.title
            attempt_to_delete.delete()
            # Invalidate cached list for student
            cache.delete(f'exam_list_{student.pk}')
            messages.success(request, f"Mock exam attempt for '{student.get_full_name()}' on '{exam_title}' has been deleted. The student can now start a fresh attempt.")
            return redirect('admin_dashboard')

        # 6) Manually Verify Email
        elif "verify_user_email" in request.POST:
            user_id = request.POST.get('user_id', '').strip()
            user_to_verify = get_object_or_404(User, pk=user_id)
            user_to_verify.is_email_verified = True
            user_to_verify.save(update_fields=['is_email_verified'])
            messages.success(request, f"Email address for student '{user_to_verify.get_full_name()}' has been manually VERIFIED.")
            return redirect('admin_dashboard')

        # 7) Manually Verify Phone
        elif "verify_user_phone" in request.POST:
            user_id = request.POST.get('user_id', '').strip()
            user_to_verify = get_object_or_404(User, pk=user_id)
            user_to_verify.is_phone_verified = True
            user_to_verify.save(update_fields=['is_phone_verified'])
            messages.success(request, f"Phone number for student '{user_to_verify.get_full_name()}' has been manually VERIFIED.")
            return redirect('admin_dashboard')

        # 8) SMTP Diagnostics Connection Test
        elif "send_test_email" in request.POST:
            test_email = request.POST.get('test_email', '').strip()
            if not test_email:
                messages.warning(request, "Please enter a valid test email address.")
            else:
                try:
                    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'info@saralpathshala.com')
                    send_mail(
                        subject="SMTP Diagnostic Test | Saral Pathshala Command Center",
                        message="SMTP diagnostics are working perfectly. This is a plain text fallback.",
                        from_email=from_email,
                        recipient_list=[test_email],
                        html_message="""
                        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; padding: 30px; border-radius: 16px; background-color: #ffffff; border: 1px solid #e2e8f0; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                            <div style="text-align: center; margin-bottom: 25px;">
                                <h1 style="color: #2d89c8; margin: 0; font-size: 24px; font-weight: 700;">SMTP Server Online</h1>
                                <p style="color: #64748b; font-size: 14px; margin: 5px 0 0 0;">Saral Pathshala Custom Diagnostics</p>
                            </div>
                            <div style="padding: 20px; background-color: #f8fafc; border-radius: 12px; border: 1px dashed #cbd5e1; margin-bottom: 25px;">
                                <p style="margin: 0 0 10px 0; color: #334155; font-size: 15px; line-height: 1.6;">
                                    Hello Administrator,
                                </p>
                                <p style="margin: 0; color: #334155; font-size: 15px; line-height: 1.6;">
                                    This diagnostic mail confirms that your Django SMTP configurations inside <code>settings.py</code> are working flawlessly! Outbound transactional emails are now ready to be delivered to students.
                                </p>
                            </div>
                            <div style="border-top: 1px solid #e2e8f0; padding-top: 15px; text-align: center; color: #94a3b8; font-size: 12px;">
                                Sent from Saral Pathshala Command Center &bull; Live SMTP Check
                            </div>
                        </div>
                        """,
                        fail_silently=False,
                    )
                    messages.success(request, f"SMTP Connection Test Successful! Test email sent successfully to {test_email}.")
                except Exception as e:
                    messages.error(request, f"SMTP Connection Test Failed! Please check your settings.py configuration. Error Details: {str(e)}")
            return redirect('admin_dashboard')

    # 1. Basic Stats
    total_students = User.objects.filter(is_staff=False, is_superuser=False).count()
    total_courses = Course.objects.filter(is_active=True).count()
    total_exams = Exam.objects.filter(is_active=True).count()
    total_attempts_count = ExamAttempt.objects.filter(is_submitted=True).count()
    
    # 2. Real-time active students
    realtime_window = timezone.now() - timedelta(hours=3)
    realtime_attempts = ExamAttempt.objects.filter(
        is_submitted=False,
        started_at__gte=realtime_window
    ).select_related('student', 'exam')
    realtime_count = realtime_attempts.count()
    
    # 3. Exam Analysis
    exams = Exam.objects.filter(is_active=True).select_related('course')
    exam_stats = []
    
    chart_exam_titles = []
    chart_avg_scores = []
    chart_attempt_counts = []
    
    for exam in exams:
        attempts = ExamAttempt.objects.filter(exam=exam, is_submitted=True)
        count = attempts.count()
        
        # Real-time students for this specific exam
        active_now = ExamAttempt.objects.filter(
            exam=exam,
            is_submitted=False,
            started_at__gte=realtime_window
        ).count()
        
        total_marks = exam.total_marks()
        
        if count > 0:
            agg = attempts.aggregate(
                avg=Avg('score'),
                max_score=Max('score'),
                min_score=Min('score')
            )
            avg_score = round(agg['avg'] or 0.0, 2)
            max_score = round(agg['max_score'] or 0.0, 2)
            min_score = round(agg['min_score'] or 0.0, 2)
            
            # Average score percentage
            avg_pct = round((avg_score / total_marks) * 100, 1) if total_marks > 0 else 0.0
            
            # Calculate distribution (Marks pattern)
            excellent = attempts.filter(score__gte=total_marks * 0.8).count()
            good = attempts.filter(score__gte=total_marks * 0.6, score__lt=total_marks * 0.8).count()
            pass_count = attempts.filter(score__gte=total_marks * 0.4, score__lt=total_marks * 0.6).count()
            fail = attempts.filter(score__lt=total_marks * 0.4).count()
        else:
            avg_score = 0.0
            max_score = 0.0
            min_score = 0.0
            avg_pct = 0.0
            excellent = good = pass_count = fail = 0

        exam_stats.append({
            'exam': exam,
            'total_attempts': count,
            'active_now': active_now,
            'average_score': avg_score,
            'average_pct': avg_pct,
            'max_score': max_score,
            'min_score': min_score,
            'total_marks': total_marks,
            'pattern': {
                'excellent': excellent,
                'good': good,
                'pass': pass_count,
                'fail': fail
            }
        })
        
        chart_exam_titles.append(exam.title[:15] + "..." if len(exam.title) > 15 else exam.title)
        chart_avg_scores.append(avg_pct)
        chart_attempt_counts.append(count)

    # 4. Student Demographics (Educational Tier Distribution)
    plus_two_count = User.objects.filter(current_level='plus_two', is_staff=False, is_superuser=False).count()
    bachelors_count = User.objects.filter(current_level='bachelors', is_staff=False, is_superuser=False).count()
    masters_count = User.objects.filter(current_level='masters', is_staff=False, is_superuser=False).count()
    
    demographics = {
        'labels': ['+2 (XI/XII)', 'Bachelors', 'Masters'],
        'counts': [plus_two_count, bachelors_count, masters_count]
    }
    
    # 5. Course Enrollee Popularity
    chart_course_names = []
    chart_course_enrollees = []
    for c in Course.objects.filter(is_active=True):
        count = Enrollment.objects.filter(course=c).count()
        chart_course_names.append(c.name[:15] + "..." if len(c.name) > 15 else c.name)
        chart_course_enrollees.append(count)

    # 6. CRM Leads / Enrollment Requests
    recent_requests = CourseEnrollmentRequest.objects.select_related('course').order_by('-created_at')[:30]
    pending_requests_count = CourseEnrollmentRequest.objects.filter(status='pending').count()
    total_requests_count = CourseEnrollmentRequest.objects.count()

    # 7. Recent Registrations & Unverified Users list
    recent_students = User.objects.filter(is_staff=False, is_superuser=False).order_by('-date_joined')[:15]
    unverified_users = User.objects.filter(is_email_verified=False, is_staff=False, is_superuser=False).order_by('-date_joined')[:20]

    # 8. Queue Analytics & Failure Monitoring
    recent_failed_emails = MailQueue.objects.filter(status=QueueStatus.FAILED).order_by('-created_at')[:10]
    recent_pending_emails = MailQueue.objects.filter(status=QueueStatus.PENDING).order_by('-created_at')[:10]
    mail_queue_stats = {
        'pending': MailQueue.objects.filter(status=QueueStatus.PENDING).count(),
        'sent': MailQueue.objects.filter(status=QueueStatus.SENT).count(),
        'failed': MailQueue.objects.filter(status=QueueStatus.FAILED).count(),
        'total': MailQueue.objects.count()
    }

    recent_failed_sms = SMSQueue.objects.filter(status=QueueStatus.FAILED).order_by('-created_at')[:10]
    recent_pending_sms = SMSQueue.objects.filter(status=QueueStatus.PENDING).order_by('-created_at')[:10]
    sms_queue_stats = {
        'pending': SMSQueue.objects.filter(status=QueueStatus.PENDING).count(),
        'sent': SMSQueue.objects.filter(status=QueueStatus.SENT).count(),
        'failed': SMSQueue.objects.filter(status=QueueStatus.FAILED).count(),
        'total': SMSQueue.objects.count()
    }

    # 9. Comprehensive Recent Exam Attempts for Retake / Review management
    recent_attempts = ExamAttempt.objects.select_related('student', 'exam').order_by('-started_at')[:25]

    context = {
        'total_students': total_students,
        'total_courses': total_courses,
        'total_exams': total_exams,
        'total_attempts_count': total_attempts_count,
        'realtime_count': realtime_count,
        'realtime_attempts': realtime_attempts,
        'exam_stats': exam_stats,
        'recent_requests': recent_requests,
        'pending_requests_count': pending_requests_count,
        'total_requests_count': total_requests_count,
        'recent_students': recent_students,
        'unverified_users': unverified_users,
        
        # Queues Context
        'recent_failed_emails': recent_failed_emails,
        'recent_pending_emails': recent_pending_emails,
        'mail_queue_stats': mail_queue_stats,
        'recent_failed_sms': recent_failed_sms,
        'recent_pending_sms': recent_pending_sms,
        'sms_queue_stats': sms_queue_stats,
        
        # Attempt Reviews
        'recent_attempts': recent_attempts,
        
        # Charts JSON
        'chart_exam_titles_json': json.dumps(chart_exam_titles),
        'chart_avg_scores_json': json.dumps(chart_avg_scores),
        'chart_attempt_counts_json': json.dumps(chart_attempt_counts),
        
        'demographics_json': json.dumps(demographics),
        'chart_course_names_json': json.dumps(chart_course_names),
        'chart_course_enrollees_json': json.dumps(chart_course_enrollees),
    }
    
    return render(request, 'admin_custom/dashboard.html', context)


@login_required
def admin_manage_enrollment_request(request, request_id, action):
    """
    Staff / Superuser CRM utility to approve, reject, or mark guest/student leads as contacted.
    If approved, automatically links/enrolls user to the course track if a student account exists.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404("You do not have permission to view this page.")

    enroll_req = get_object_or_404(CourseEnrollmentRequest, pk=request_id)
    
    if action == 'approve':
        enroll_req.status = 'approved'
        enroll_req.save()
        
        # Auto-create user enrollment if the user exists in database
        student = User.objects.filter(email=enroll_req.email).first()
        if not student and enroll_req.phone:
            student = User.objects.filter(phone=enroll_req.phone).first()
            
        if student:
            # Check for existing enrollment
            already_enrolled = Enrollment.objects.filter(user=student, course=enroll_req.course).exists()
            if not already_enrolled:
                Enrollment.objects.create(
                    user=student,
                    course=enroll_req.course,
                    enrolled_by=request.user
                )
                messages.success(request, f"Enrollment lead approved! Student '{student.get_full_name()}' has been enrolled in '{enroll_req.course.name}' successfully.")
            else:
                messages.success(request, f"Enrollment lead approved! Student was already enrolled.")
        else:
            messages.warning(request, f"Request approved in CRM, but no user account could be located for email '{enroll_req.email}' or phone '{enroll_req.phone}'. Please register the student first.")
            
    elif action == 'contact':
        enroll_req.status = 'contacted'
        enroll_req.save()
        messages.info(request, f"Enrollment lead status updated to Contacted / Followed Up.")
        
    elif action == 'reject':
        enroll_req.status = 'rejected'
        enroll_req.save()
        messages.error(request, f"Enrollment lead rejected.")
        
    return redirect('admin_dashboard')


@login_required
def admin_export_exam_results(request, exam_id):
    """
    Export all submitted exam attempts for a specific exam as a CSV.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        raise Http404("You do not have permission to perform this action.")

    import csv
    from django.http import HttpResponse

    exam = get_object_or_404(Exam, pk=exam_id)
    attempts = ExamAttempt.objects.filter(exam=exam, is_submitted=True).select_related('student')
    
    response = HttpResponse(content_type='text/csv')
    filename = f"results_{exam.slug}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Student Name',
        'Student Email',
        'Student Phone',
        'Exam Title',
        'Course Title',
        'Score Obtained',
        'Total Marks',
        'Correct Answers',
        'Wrong Answers',
        'Unattempted Questions',
        'Accuracy %',
        'Started At',
        'Submitted At'
    ])
    
    total_marks = exam.total_marks()
    for att in attempts:
        pct = round((att.score / total_marks) * 100, 1) if total_marks > 0 else 0.0
        writer.writerow([
            att.student.full_name,
            att.student.email,
            att.student.phone or 'N/A',
            exam.title,
            exam.course.name,
            att.score,
            total_marks,
            att.correct_count,
            att.wrong_count,
            att.unattempted_count,
            pct,
            att.started_at.strftime('%Y-%m-%d %H:%M:%S'),
            att.completed_at.strftime('%Y-%m-%d %H:%M:%S') if att.completed_at else 'N/A'
        ])
        
    return response