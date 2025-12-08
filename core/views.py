from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from scheduling.models import (
    Subject, 
    Curriculum,
    Semester,
)
from authapi.views import has_role
from django.db import transaction
from core.models import (
    User, 
    Role, 
    Instructor, 
    Student, 
    UserLogin,
)
from instructors.models import (
    TeachingHistory, 
    InstructorExperience, 
    InstructorCredentials
)
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.db.models import Q
from auditlog.models import LogEntry
from datetime import date



# ---------- Home ----------
def home(request):
    return render(request, 'home.html')

def checkUsernameAvailability(request):
    username = request.GET.get('value', '').strip()
    exists = User.objects.filter(username=username).exists()
    return JsonResponse({
        'isAvailable': not exists,
        'message': 'Username available.' if not exists else 'Username already taken.'
    })

@require_GET
def checkInstructorIdAvailability(request):
    instructorId = request.GET.get('value', '').strip()
    exists = Instructor.objects.filter(instructorId=instructorId).exists()
    return JsonResponse({
        'isAvailable': not exists,
        'message': 'Instructor ID available.' if not exists else 'Instructor ID already taken.'
    })

@require_GET
def checkStudentIdAvailability(request):
    studentId = request.GET.get('value', '').strip()
    exists = Student.objects.filter(studentId=studentId).exists()
    return JsonResponse({
        'isAvailable': not exists,
        'message': 'Student ID available.' if not exists else 'Student ID already taken.'
    })


@login_required
@has_role('deptHead')
def auditlog_view(request):
    logs = LogEntry.objects.select_related('actor', 'content_type').order_by('-timestamp')[:100]

    return render(request, 'auditlog/auditlogList.html', {'logs': logs})


# ---------- Subjects ----------
@login_required
@has_role('deptHead')
def subjectList(request):
    curriculums = Curriculum.objects.order_by('-createdAt')
    curriculum_id = request.GET.get('curriculumId')
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    if not curriculum_id and curriculums.exists():
        selected_curriculum = curriculums.first()
    else:
        selected_curriculum = get_object_or_404(Curriculum, pk=curriculum_id)

    subjects = Subject.objects.filter(curriculum=selected_curriculum)

    if query:
        subjects = subjects.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query) |
            Q(subjectTopics__icontains=query)
        )

    paginator = Paginator(subjects, 10)
    page_obj = paginator.get_page(page)

    return render(request, 'core/subjects/list.html', {
        'subjects': page_obj,
        'curriculums': curriculums,
        'selectedCurriculumId': selected_curriculum.curriculumId,
        'query': query,
    })


@login_required
@has_role('deptHead')
def subjectListLive(request):
    curriculums = Curriculum.objects.order_by('-createdAt')
    curriculum_id = request.GET.get('curriculumId')
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    if not curriculum_id and curriculums.exists():
        selected_curriculum = curriculums.first()
    else:
        selected_curriculum = get_object_or_404(Curriculum, pk=curriculum_id)

    subjects = Subject.objects.filter(curriculum=selected_curriculum)

    if query:
        subjects = subjects.filter(
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(description__icontains=query) |
            Q(subjectTopics__icontains=query)
        )

    paginator = Paginator(subjects, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("core/subjects/_list_table.html", {
        "subjects": page_obj,
        "selectedCurriculumId": selected_curriculum.curriculumId,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('deptHead')
def subjectCreate(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        name = request.POST.get('name')
        curriculumId = request.POST.get('curriculumId')
        curriculum = get_object_or_404(Curriculum, pk=curriculumId)
        units = request.POST.get('units')
        defaultTerm = request.POST.get('defaultTerm')
        yearLevel = request.POST.get('yearLevel')
        durationMinutes = request.POST.get('durationMinutes')
        hasLab = request.POST.get('hasLab') == 'on'
        labDurationMinutes = request.POST.get('labDurationMinutes') or None
        isPriorityForRooms = request.POST.get('isPriorityForRooms') == 'on'
        description = request.POST.get('description') or ''  # 🆕 Added field
        subjectTopics = request.POST.get('subjectTopics') or ''
        notes = request.POST.get('notes') or ''

        if Subject.objects.filter(code=code).exists():
            messages.error(request, 'Subject with this code already exists.')
        else:
            Subject.objects.create(
                code=code,
                name=name,
                curriculum=curriculum,
                units=units,
                defaultTerm=defaultTerm,
                yearLevel=yearLevel,
                durationMinutes=durationMinutes,
                hasLab=hasLab,
                labDurationMinutes=labDurationMinutes,
                isPriorityForRooms=isPriorityForRooms,
                description=description, 
                subjectTopics=subjectTopics,
                notes=notes
            )
            messages.success(request, 'Subject created successfully.')
            return redirect('subjectList')

    curriculums = Curriculum.objects.all()
    return render(request, 'core/subjects/create.html', {'curriculums': curriculums})


@login_required
@has_role('deptHead')
def subjectUpdate(request, subjectCode):
    subject = get_object_or_404(Subject, code=subjectCode)

    if request.method == 'POST':
        newCode = request.POST.get('code')
        if newCode and newCode != subject.code:
            # Optional: check if new code already exists
            if Subject.objects.filter(code=newCode).exclude(subjectId=subject.subjectId).exists():
                messages.error(request, f'Subject code "{newCode}" is already taken.')
                return redirect('subjectUpdate', subjectCode=subject.code)

            subject.code = newCode

        subject.name = request.POST.get('name')
        curriculumId = request.POST.get('curriculumId')
        subject.curriculum = get_object_or_404(Curriculum, pk=curriculumId)
        subject.units = int(request.POST.get('units'))
        subject.defaultTerm = int(request.POST.get('defaultTerm'))
        subject.yearLevel = int(request.POST.get('yearLevel'))
        subject.durationMinutes = int(request.POST.get('durationMinutes'))
        subject.hasLab = 'hasLab' in request.POST
        labDuration = request.POST.get('labDurationMinutes') or None
        subject.labDurationMinutes = int(labDuration) if labDuration else None
        subject.isPriorityForRooms = 'isPriorityForRooms' in request.POST
        subject.description = request.POST.get('description') or '' 
        subject.subjectTopics = request.POST.get('subjectTopics') or ''
        subject.notes = request.POST.get('notes') or ''

        subject.save()
        messages.success(request, 'Subject updated successfully.')
        return redirect('subjectList')

    curriculums = Curriculum.objects.all()
    return render(request, 'core/subjects/update.html', {
        'subject': subject,
        'curriculums': curriculums
    })



@login_required
@has_role('deptHead')
def subjectDelete(request, subjectCode):
    subject = get_object_or_404(Subject, code=subjectCode)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, 'Subject deleted.')
        return redirect('subjectList')
    return render(request, 'core/subjects/delete.html', {'subject': subject})



# ---------- Instructor Accounts ----------
@login_required
@has_role('deptHead')
def instructorAccountList(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    instructor_logins = UserLogin.objects.select_related('user', 'instructor') \
        .filter(user__roles__name='instructor', instructor__isnull=False) \
        .distinct()

    # Attach readable names
    for login in instructor_logins:
        login.instructor_display_name = login.instructor.full_name

    if query:
        instructor_logins = [
            l for l in instructor_logins
            if query.lower() in l.instructor_display_name.lower()
            or query.lower() in l.user.email.lower()
            or query.lower() in l.instructor.instructorId.lower()
        ]

    paginator = Paginator(instructor_logins, 10)
    page_obj = paginator.get_page(page)

    return render(request, "core/instructors/list.html", {
        "instructorLogins": page_obj,
        "query": query
    })


@login_required
@has_role('deptHead')
def instructorAccountListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    instructor_logins = UserLogin.objects.select_related('user', 'instructor') \
        .filter(user__roles__name='instructor', instructor__isnull=False) \
        .distinct()

    for login in instructor_logins:
        login.instructor_display_name = login.instructor.full_name

    if query:
        instructor_logins = [
            l for l in instructor_logins
            if query.lower() in l.instructor_display_name.lower()
            or query.lower() in l.user.email.lower()
            or query.lower() in l.instructor.instructorId.lower()
        ]

    paginator = Paginator(instructor_logins, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("core/instructors/_list_table.html", {
        "instructorLogins": page_obj
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })

@login_required
@has_role('deptHead')
@transaction.atomic
def instructorAccountCreate(request):
    from instructors.models import InstructorRank, InstructorDesignation, InstructorAcademicAttainment

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        firstName = request.POST.get('firstName')
        lastName = request.POST.get('lastName')
        instructorId = request.POST.get('instructorId')
        employmentType = request.POST.get('employmentType')
        rank_id = request.POST.get('rank')
        designation_id = request.POST.get('designation')
        attainment_id = request.POST.get('academicAttainment')

        # Validation checks
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        elif Instructor.objects.filter(instructorId=instructorId).exists():
            messages.error(request, 'Instructor ID already exists.')
        else:
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                firstName=firstName,
                lastName=lastName,
                isActive=True
            )

            # Assign role
            instructorRole = Role.objects.get(name='instructor')
            user.roles.add(instructorRole)

            # Create instructor with proper FK relations
            instructor = Instructor.objects.create(
                instructorId=instructorId,
                employmentType=employmentType,
                rank=InstructorRank.objects.filter(pk=rank_id).first() if rank_id else None,
                designation=InstructorDesignation.objects.filter(pk=designation_id).first() if designation_id else None,
                academicAttainment=InstructorAcademicAttainment.objects.filter(pk=attainment_id).first() if attainment_id else None,
            )

            # Link UserLogin
            UserLogin.objects.create(user=user, instructor=instructor)

            messages.success(request, 'Instructor account successfully created.')
            return redirect('instructorAccountList')

    context = {
        'ranks': InstructorRank.objects.all(),
        'designations': InstructorDesignation.objects.all(),
        'attainments': InstructorAcademicAttainment.objects.all(),
    }
    return render(request, 'core/instructors/create.html', context)


@login_required
@has_role('deptHead')
@transaction.atomic
def instructorAccountUpdate(request, userId):
    from instructors.models import InstructorRank, InstructorDesignation, InstructorAcademicAttainment

    user = get_object_or_404(User, pk=userId)
    user_login = get_object_or_404(UserLogin, user=user)

    if not user_login.instructor:
        messages.error(request, "This account is not linked to any instructor.")
        return redirect('instructorAccountList')

    instructor = user_login.instructor

    if request.method == 'POST':
        # Update User info
        user.firstName = request.POST.get('firstName')
        user.lastName = request.POST.get('lastName')
        user.email = request.POST.get('email')
        user.save()

        # Update Instructor info
        newInstructorId = request.POST.get('instructorId')
        employmentType = request.POST.get('employmentType')
        rank_id = request.POST.get('rank')
        designation_id = request.POST.get('designation')
        attainment_id = request.POST.get('academicAttainment')

        if newInstructorId and newInstructorId != instructor.instructorId:
            if Instructor.objects.filter(instructorId=newInstructorId).exclude(pk=instructor.pk).exists():
                messages.error(request, 'Instructor ID already exists.')
                return redirect('instructorAccountUpdate', userId=user.userId)
            instructor.instructorId = newInstructorId

        instructor.employmentType = employmentType
        instructor.rank = InstructorRank.objects.filter(pk=rank_id).first() if rank_id else None
        instructor.designation = InstructorDesignation.objects.filter(pk=designation_id).first() if designation_id else None
        instructor.academicAttainment = InstructorAcademicAttainment.objects.filter(pk=attainment_id).first() if attainment_id else None

        instructor.save()

        messages.success(request, 'Instructor account updated successfully.')
        return redirect('instructorAccountList')

    context = {
        'user': user,
        'instructor': instructor,
        'ranks': InstructorRank.objects.all(),
        'designations': InstructorDesignation.objects.all(),
        'attainments': InstructorAcademicAttainment.objects.all(),
    }
    return render(request, 'core/instructors/update.html', context)



@login_required
@has_role('deptHead')
@transaction.atomic
def instructorAccountDelete(request, userId):
    user = get_object_or_404(User, pk=userId)

    if request.method == 'POST':
        try:
            user.delete()
            messages.success(request, 'Instructor account deleted.')
            return redirect('instructorAccountList')
        except IntegrityError:
            messages.error(request, 'Cannot delete instructor account: It has linked records in the database.')
            return redirect('instructorAccountList')

    return render(request, 'core/instructors/delete.html', {'user': user})



# ---------- Student Accounts ----------
@login_required
@has_role('deptHead')
def studentAccountList(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    student_logins = UserLogin.objects.select_related('user', 'student') \
        .filter(user__roles__name='student', student__isnull=False) \
        .distinct()

    # Attach readable names
    for login in student_logins:
        login.student_display_name = login.student.full_name

    if query:
        student_logins = [
            l for l in student_logins
            if query.lower() in l.student_display_name.lower()
            or query.lower() in l.user.email.lower()
            or query.lower() in l.student.studentId.lower()
        ]

    paginator = Paginator(student_logins, 10)
    page_obj = paginator.get_page(page)

    return render(request, "core/students/list.html", {
        "studentLogins": page_obj,
        "query": query
    })


@login_required
@has_role('deptHead')
def studentAccountListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    student_logins = UserLogin.objects.select_related('user', 'student') \
        .filter(user__roles__name='student', student__isnull=False) \
        .distinct()

    for login in student_logins:
        login.student_display_name = login.student.full_name

    if query:
        student_logins = [
            l for l in student_logins
            if query.lower() in l.student_display_name.lower()
            or query.lower() in l.user.email.lower()
            or query.lower() in l.student.studentId.lower()
        ]

    paginator = Paginator(student_logins, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("core/students/_list_table.html", {
        "studentLogins": page_obj
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@transaction.atomic
def studentAccountCreate(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        firstName = request.POST.get('firstName')
        lastName = request.POST.get('lastName')
        middleInitial = request.POST.get('middleInitial')
        studentId = request.POST.get('studentId')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        elif Student.objects.filter(studentId=studentId).exists():
            messages.error(request, 'Student ID already exists.')
        else:
            # Create User
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                firstName=firstName,
                lastName=lastName,
                middleInitial=middleInitial,
                isActive=True
            )

            # Assign Role
            studentRole = Role.objects.get(name='student')
            user.roles.add(studentRole)

            # Create Student Profile
            student = Student.objects.create(studentId=studentId)

            # Link in UserLogin
            UserLogin.objects.create(user=user, student=student)

            messages.success(request, 'Student account successfully created.')
            return redirect('studentAccountList')

    return render(request, 'core/students/create.html')

@login_required
@has_role('deptHead')
@has_role('student')
@transaction.atomic
def studentAccountUpdate(request, userId):
    user = get_object_or_404(User, pk=userId)
    user_login = get_object_or_404(UserLogin, user=user)

    if not user_login.student:
        messages.error(request, "This account is not linked to any student.")
        return redirect('studentAccountList')

    student = user_login.student

    if request.method == 'POST':
        # Update User info
        user.firstName = request.POST.get('firstName')
        user.lastName = request.POST.get('lastName')
        user.middleInitial = request.POST.get('middleInitial')
        user.email = request.POST.get('email')
        user.save()

        # Update Student info
        newStudentId = request.POST.get('studentId')

        if newStudentId and newStudentId != student.studentId:
            if Student.objects.filter(studentId=newStudentId).exclude(pk=student.pk).exists():
                messages.error(request, 'Student ID already exists.')
                return redirect('studentAccountUpdate', userId=user.userId)
            student.studentId = newStudentId

        student.save()

        messages.success(request, 'Student account updated successfully.')
        return redirect('studentAccountList')

    return render(request, 'core/students/update.html', {
        'user': user,
        'student': student
    })


# ------------ Recommendation System ----------
def normalize_year(value):
    """Extract numeric start year from '2020-2021'."""
    if not value: return None
    try:
        # We must convert to string before splitting, as the value might be an object/None initially
        return int(str(value).split("-")[0].strip())
    except (ValueError, AttributeError):
        return None

def recommendation_dashboard(request):
    subjects = Subject.objects.filter(isActive=True).values("subjectId", "code", "name")
    semesters = Semester.objects.values_list("academicYear", flat=True).distinct()
    years = sorted({normalize_year(y) for y in semesters if normalize_year(y)})
    
    instructors = Instructor.objects.all().order_by('userlogin__user__lastName')

    context = {
        "subjects": sorted(subjects, key=lambda s: s["code"]),
        "years": years,
        "instructors": instructors,
    }
    return render(request, "core/recommendation/recommendationDashboard.html", context)

def recommendation_data(request):
    # 1. Parse Filters
    subject_names = request.GET.getlist("subjects[]")
    year_from = normalize_year(request.GET.get("year_from"))
    year_to = normalize_year(request.GET.get("year_to"))
    
    # 2. Base Queryset
    # FIX: Instructor.objects.all() is used
    instructors_qs = Instructor.objects.all().select_related('rank').prefetch_related(
        'teachingHistory__semester',
        'experiences',
        'credentials__relatedSubjects'
    )

    results = []

    for inst in instructors_qs:
        
        # --- Metric 1: Years Taught (Count unique academic years taught) ---
        history_qs = inst.teachingHistory.all()
        
        # Subject Filter
        if subject_names and "all" not in subject_names:
            # Note: Assuming 'subject' is a ForeignKey on TeachingHistory
            history_qs = history_qs.filter(subject__name__in=subject_names)
        
        # Year Filter and collection of unique years
        years_taught_set = set()
        for h in history_qs:
            y = normalize_year(h.semester.academicYear)
            if y:
                if (not year_from or y >= year_from) and (not year_to or y <= year_to):
                    years_taught_set.add(y)
        
        years_taught_count = len(years_taught_set)

        # --- Metric 2: External/Teaching Experience (Years) ---
        exp_years = 0.0
        relevant_exps = inst.experiences.filter(experienceType="Teaching Experience")
        
        if subject_names and "all" not in subject_names:
             # Filtering by relatedSubjects M2M field
             relevant_exps = relevant_exps.filter(relatedSubjects__name__in=subject_names).distinct()
        
        for exp in relevant_exps:
            start = exp.startDate.year
            end = exp.endDate.year if exp.endDate else date.today().year
            
            # Determine the intersection of the experience range and the filter range
            search_start = year_from if year_from else 0
            search_end = year_to if year_to else date.today().year # Default to current year for 'to' filter
            
            actual_start = max(start, search_start)
            actual_end = min(end, search_end)
            
            # Add the duration of the overlapping period
            if actual_start <= actual_end:
                exp_years += (actual_end - actual_start) + 1 

        # --- Metric 3: Relevant Credentials ---
        cred_qs = inst.credentials.all()
        if subject_names and "all" not in subject_names:
            # Filtering by relatedSubjects M2M field on InstructorCredentials
            cred_qs = cred_qs.filter(relatedSubjects__name__in=subject_names)
        
        cred_count = cred_qs.distinct().count()

        # --- Build Result Object ---
        results.append({
            "id": inst.instructorId,
            "name": inst.full_name,
            "rank": inst.rank.name if hasattr(inst, 'rank') and inst.rank else "N/A", 
            "years_taught": years_taught_count,
            "experience_years": round(exp_years, 1),
            "credential_count": cred_count
        })

    # Default sort by Years Taught descending
    results.sort(key=lambda x: x['years_taught'], reverse=True)

    return JsonResponse({"data": results})