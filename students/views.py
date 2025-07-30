from django.shortcuts import render, redirect
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from core.models import User, Role, Student, UserLogin
from authapi.views import has_role  
from django.contrib.auth.decorators import login_required
from students.models import Enrollment
from scheduling.models import Schedule
from django.core.paginator import Paginator
from django.db.models import Q
from django.template.loader import render_to_string
from django.http import JsonResponse

def studentAccountCreate(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        firstName = request.POST.get('firstName')
        lastName = request.POST.get('lastName')
        middleInitial = request.POST.get('middleInitial')
        studentId = request.POST.get('studentId')

        if not all([username, email, password, firstName, lastName, studentId]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('studentAccountCreate')

        # 🔎 Duplicate checks
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken.")
            return redirect('studentAccountCreate')

        if User.objects.filter(email=email).exists():
            messages.error(request, f"Email '{email}' is already registered.")
            return redirect('studentAccountCreate')

        if Student.objects.filter(studentId=studentId).exists():
            messages.error(request, f"Student ID '{studentId}' already exists.")
            return redirect('studentAccountCreate')

        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    firstName=firstName,
                    lastName=lastName,
                    middleInitial=middleInitial or None
                )

                studentRole = Role.objects.get(name='student')
                user.roles.add(studentRole)

                student = Student.objects.create(studentId=studentId)

                UserLogin.objects.create(user=user, student=student)

                messages.success(request, f"Student account for '{username}' created successfully.")
                return redirect('studentDashboard')

        except Role.DoesNotExist:
            messages.error(request, "Student role is not configured in the system.")
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")

    return render(request, 'students/studentAccountCreate.html')


# ---------- Student Enrollement ----------
@login_required
@has_role('student')
def enrollmentList(request):
    user_login = get_object_or_404(UserLogin, user=request.user)
    if not user_login.student:
        messages.error(request, "Student profile not found.")
        return redirect('dashboard')

    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    enrollments = Enrollment.objects.filter(student=user_login.student) \
        .select_related('schedule__offer__subject', 'schedule__section') \
        .order_by('-enrollmentDate')

    if query:
        enrollments = enrollments.filter(
            Q(schedule__offer__subject__code__icontains=query) |
            Q(schedule__offer__subject__name__icontains=query) |
            Q(schedule__section__sectionCode__icontains=query) |
            Q(schedule__day__icontains=query)
        )

    paginator = Paginator(enrollments, 8)
    page_obj = paginator.get_page(page)

    return render(request, "students/enrollments/list.html", {
        "enrollments": page_obj,
        "query": query,
    })


@login_required
@has_role('student')
def enrollmentListLive(request):
    user_login = get_object_or_404(UserLogin, user=request.user)
    if not user_login.student:
        return JsonResponse({"html": "<p>Error: Student profile not found.</p>"})

    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    enrollments = Enrollment.objects.filter(student=user_login.student) \
        .select_related('schedule__offer__subject', 'schedule__section') \
        .order_by('-enrollmentDate')

    if query:
        enrollments = enrollments.filter(
            Q(schedule__offer__subject__code__icontains=query) |
            Q(schedule__offer__subject__name__icontains=query) |
            Q(schedule__section__sectionCode__icontains=query) |
            Q(schedule__day__icontains=query)
        )

    paginator = Paginator(enrollments, 8)
    page_obj = paginator.get_page(page)

    html = render_to_string("students/enrollments/_table.html", {
        "enrollments": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
    })


@login_required
@has_role('student')
def enrollmentCreate(request):
    user_login = get_object_or_404(UserLogin, user=request.user)

    if not user_login.student:
        messages.error(request, "Student profile not found.")
        return redirect('dashboard')

    schedules = Schedule.objects.select_related('offer__subject', 'section').order_by('offer__subject__code', 'section__sectionCode')

    if request.method == 'POST':
        scheduleId = request.POST.get('schedule')
        schedule = get_object_or_404(Schedule, scheduleId=scheduleId)

        # Prevent duplicate enrollments
        existing = Enrollment.objects.filter(student=user_login.student, schedule=schedule).exists()
        if existing:
            messages.warning(request, 'You are already enrolled in this schedule.')
            return redirect('enrollmentList')

        Enrollment.objects.create(
            student=user_login.student,
            schedule=schedule
        )
        messages.success(request, 'Enrollment added successfully.')
        return redirect('enrollmentList')

    return render(request, 'students/enrollments/create.html', {
        'schedules': schedules
    })


@login_required
@has_role('student')
def enrollmentUpdate(request, enrollmentId):
    user_login = get_object_or_404(UserLogin, user=request.user)

    if not user_login.student:
        messages.error(request, "Student profile not found.")
        return redirect('dashboard')

    enrollment = get_object_or_404(Enrollment, enrollmentId=enrollmentId, student=user_login.student)
    schedules = Schedule.objects.select_related('offer__subject', 'section').order_by('offer__subject__code', 'section__sectionCode')

    if request.method == 'POST':
        scheduleId = request.POST.get('schedule')
        new_schedule = get_object_or_404(Schedule, scheduleId=scheduleId)

        # Prevent duplicate enrollments
        if Enrollment.objects.filter(student=user_login.student, schedule=new_schedule).exclude(enrollmentId=enrollmentId).exists():
            messages.warning(request, 'You are already enrolled in this schedule.')
            return redirect('enrollmentList')

        enrollment.schedule = new_schedule
        enrollment.save()

        messages.success(request, 'Enrollment updated successfully.')
        return redirect('enrollmentList')

    return render(request, 'students/enrollments/update.html', {
        'enrollment': enrollment,
        'schedules': schedules
    })


@login_required
@has_role('student')
def enrollmentDelete(request, enrollmentId):
    user_login = get_object_or_404(UserLogin, user=request.user)

    if not user_login.student:
        messages.error(request, "Student profile not found.")
        return redirect('dashboard')

    enrollment = get_object_or_404(Enrollment, enrollmentId=enrollmentId, student=user_login.student)

    if request.method == 'POST':
        enrollment.delete()
        messages.success(request, 'Enrollment deleted successfully.')
        return redirect('enrollmentList')

    return render(request, 'students/enrollments/delete.html', {'enrollment': enrollment})