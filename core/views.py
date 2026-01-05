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
    InstructorExperience, 
    InstructorCredentials,
    InstructorLegacyExperience,
)
from aimatching.models import (
    InstructorSubjectMatch,
    InstructorSubjectMatchHistory,
)
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from auditlog.models import LogEntry
from datetime import date
from django.db.models import Q, Count, F, Value, Case, When, IntegerField
from django.utils import timezone
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from .forms import InstructorProfileForm, DepartmentHeadAssignmentForm
from django.core.exceptions import PermissionDenied



# ---------- Home ----------
def home(request):
    return render(request, 'home.html')

@login_required
def checkUsernameAvailability(request):
    username = request.GET.get('username', None)
    if not username:
        return JsonResponse({'is_taken': False})
        
    is_taken = User.objects.filter(username__iexact=username).exclude(pk=request.user.pk).exists()
    
    return JsonResponse({'is_taken': is_taken})

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
def manageDeptHead(request):
    user = request.user
    isAdmin = user.is_superuser
    isCurrentHead = user.roles.filter(name='deptHead').exists()

    # SECURITY: Only Admin or the Current Dept Head can enter
    if not (isAdmin or isCurrentHead):
        raise PermissionDenied("You are not authorized to manage Department Leadership.")

    try:
        deptHeadRole = Role.objects.get(name='deptHead')
    except Role.DoesNotExist:
        messages.error(request, "Critical: 'deptHead' role missing.")
        return redirect('admin:index')

    # Find the current leader (exclude admin from display logic)
    currentHeadInstructor = Instructor.objects.filter(
        userlogin__user__roles__name='deptHead',
        userlogin__user__isActive=True
    ).exclude(userlogin__user__is_superuser=True).first()

    if request.method == 'POST':
        form = DepartmentHeadAssignmentForm(request.POST)
        if form.is_valid():
            newInstructor = form.cleaned_data['newHead']
            password = form.cleaned_data['confirmPassword']

            # --- VERIFICATION LOGIC ---
            isAuthorized = False
            
            if isAdmin:
                isAuthorized = True
            elif isCurrentHead:
                if not password:
                    messages.error(request, "You must enter your password to authorize this transfer.")
                elif not user.check_password(password):
                    messages.error(request, "Incorrect password. Transfer denied.")
                else:
                    isAuthorized = True
            
            # --- TRANSFER LOGIC ---
            if isAuthorized:
                try:
                    with transaction.atomic():
                        # 1. REMOVE role from ALL old heads
                        oldLeads = UserLogin.objects.filter(
                            user__roles__name='deptHead'
                        ).select_related('user')

                        for login in oldLeads:
                            if not login.user.is_superuser: 
                                login.user.roles.remove(deptHeadRole)
                                login.user.save()

                        # 2. ADD role to New Head
                        newLogin = UserLogin.objects.filter(instructor=newInstructor).first()
                        if newLogin and newLogin.user:
                            newLogin.user.roles.add(deptHeadRole)
                            newLogin.user.save()

                            actionMsg = "overridden" if isAdmin else "transferred"
                            messages.success(request, f"Leadership successfully {actionMsg} to {newInstructor.full_name}.")
                            return redirect('manageDeptHead')
                        else:
                            messages.error(request, "Selected instructor has no User account linked.")

                except Exception as e:
                    messages.error(request, f"Database error: {str(e)}")

    else:
        form = DepartmentHeadAssignmentForm()

    context = {
        'form': form,
        'currentHead': currentHeadInstructor,
        'isAdmin': isAdmin, 
    }
    return render(request, 'core/manageDeptHead.html', context)


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


@login_required
@has_role('deptHead')
def recommendInstructors(request):
    """
    Generates professional development recommendations using:
    1. REAL Profile Data (Academic Attainment, Rank, Max Years)
    2. Accurate Experience Calculation (Max of Legacy + System Years)
    """
    
    # --- GET FILTER PARAMETERS ---
    search_query = request.GET.get('q', '')
    filter_type = request.GET.get('type', '')

    # --- 1. DB QUERY ---
    matches_query = InstructorSubjectMatch.objects.filter(
        isLatest=True,
        isRecommended=True
    ).select_related(
        'instructor', 
        'subject',
        'instructor__rank',               # e.g., "Instructor I"
        'instructor__academicAttainment'  # e.g., "Doctorate Degree"
    ).prefetch_related(
        'instructor__userlogin_set__user',
        'instructor__credentials',        # Secondary check
        'instructor__experiences',        # Industry jobs
        'instructor__legacy_experiences', # Manual History
        'instructor__system_assignments__semester' # For accurate system counting
    )

    if search_query:
        matches_query = matches_query.filter(
            Q(instructor__userlogin__user__firstName__icontains=search_query) |
            Q(instructor__userlogin__user__lastName__icontains=search_query) |
            Q(subject__code__icontains=search_query) |
            Q(subject__description__icontains=search_query)
        )

    training_programs = []
    
    # --- HELPER: SUBJECT CATEGORY ---
    def get_category(subject):
        name = (subject.description or subject.name or "").lower()
        if any(x in name for x in ['security', 'cyber', 'forensic']): return 'Security'
        if any(x in name for x in ['blockchain', 'ai', 'intelligence', 'robotics']): return 'Emerging'
        if any(x in name for x in ['programming', 'web', 'dev', 'software']): return 'Dev'
        if any(x in name for x in ['history', 'ethics', 'society', 'gen ed']): return 'GenEd'
        return 'Core_IT'

    for match in matches_query:
        instructor = match.instructor
        subject = match.subject
        category = get_category(subject)
        
        # --- A. ACCURATE DEGREE CHECK ---
        # 1. Primary Source: Academic Attainment (The main dropdown in profile)
        attainment_name = (instructor.academicAttainment.name if instructor.academicAttainment else "").lower()
        
        has_phd = 'doctor' in attainment_name or 'phd' in attainment_name
        has_masters = 'master' in attainment_name
        
        # 2. Secondary Source: Credentials List (Backup if Attainment is N/A)
        if not has_phd and not has_masters:
            cred_types = [c.credentialType for c in instructor.credentials.all()]
            has_phd = 'PhD' in cred_types
            has_masters = 'Masters' in cred_types

        # --- B. ACCURATE EXPERIENCE CALCULATION ---
        
        # 1. Legacy Years: Use MAX, not Sum. 
        # (If I taught 3 subjects for 1 year in 2024, my experience is 1 year, not 3).
        legacy_years_list = [l.priorYearsExperience for l in instructor.legacy_experiences.all()]
        legacy_years = max(legacy_years_list) if legacy_years_list else 0
        
        # 2. System Years: Count Unique Semesters / 2
        unique_semesters = set(
            a.semester.semesterId for a in instructor.system_assignments.all()
        )
        system_years = len(unique_semesters) / 2.0 
        
        # Total
        total_teaching_years = float(legacy_years) + system_years
        
        # 3. Industry Experience
        industry_jobs = [e for e in instructor.experiences.all() if e.experienceType == 'Industry']
        industry_count = len(industry_jobs)
        
        # 4. Rank
        rank_name = (instructor.rank.name if instructor.rank else "").lower()
        is_senior = 'associate' in rank_name or 'professor' in rank_name
        is_instructor_rank = 'instructor' in rank_name

        rec = None 

        # --- C. DETERMINE RECOMMENDATION ---

        # SCENARIO 1: PRACTITIONER (Needs Master's)
        if industry_count >= 2 and not has_masters and not has_phd:
            rec = {
                'type': 'Formal Education',
                'title': "Master's Degree Track",
                'reason': f"Instructor has industry exp ({industry_count} roles) but needs a Master's (Current: {attainment_name or 'Bachelors'}) for tenure.",
                'action': 'Faculty Scholarship',
                'priority': 'High',
                'color': 'red'
            }

        # SCENARIO 2: ACADEMIC (Has Degree, Needs Tech Skills)
        elif (has_masters or has_phd) and industry_count == 0 and category in ['Dev', 'Security']:
             rec = {
                'type': 'Technical Workshop',
                'title': 'Industry Immersion',
                'reason': 'Instructor has advanced degrees but needs practical industry exposure.',
                'action': 'Bootcamp',
                'priority': 'Medium',
                'color': 'orange'
            }

        # SCENARIO 3: VETERAN (Senior or >10 Years)
        elif is_senior or total_teaching_years > 10:
            if category == 'Emerging':
                rec = {
                    'type': 'Global Summit',
                    'title': f'Tech Summit: {subject.code}',
                    'reason': 'Senior faculty should attend global conferences to keep curriculum updated.',
                    'action': 'Conference Funding',
                    'priority': 'High',
                    'color': 'indigo'
                }
            elif category == 'GenEd' and not has_phd:
                 rec = {
                    'type': 'Formal Education',
                    'title': 'PhD Completion',
                    'reason': 'Senior GenEd faculty required to complete Doctorate for accreditation.',
                    'action': 'Dissertation Grant',
                    'priority': 'High',
                    'color': 'red'
                }
            else:
                 rec = {
                    'type': 'Research & Publication',
                    'title': 'Research Output',
                    'reason': 'Senior faculty are expected to produce research outputs.',
                    'action': 'Load Release',
                    'priority': 'Low',
                    'color': 'emerald'
                }

        # SCENARIO 4: STAGNANT (Long Service, Low Rank)
        elif total_teaching_years > 5 and is_instructor_rank and has_masters:
             rec = {
                'type': 'Career Development',
                'title': 'Promotion Review',
                'reason': f'Instructor has served {total_teaching_years:.1f} years with a Master\'s but remains at Instructor rank.',
                'action': 'HR Evaluation',
                'priority': 'Medium',
                'color': 'blue'
            }

        # SCENARIO 5: GENERAL UPGRADING
        elif category in ['Dev', 'Core_IT']:
            rec = {
                'type': 'Skill Upgrading',
                'title': f'Refresher: {subject.description}',
                'reason': 'Recommended refresher seminar to stay updated with modern tools.',
                'action': 'Attend Seminar',
                'priority': 'Low',
                'color': 'teal'
            }

        # --- APPEND ---
        if rec:
            rec['instructor'] = instructor
            rec['subject'] = subject
            
            # Display Logic
            if has_phd: degree_display = "PhD"
            elif has_masters: degree_display = "Masters"
            else: degree_display = "Bachelors"

            rec['metrics'] = {
                'years': f"{total_teaching_years:.1f}",
                'industry': industry_count,
                'degree': degree_display,
                'rank': instructor.rank.name if instructor.rank else "N/A"
            }
            training_programs.append(rec)

    # --- FILTERING ---
    if filter_type:
        training_programs = [t for t in training_programs if t['type'] == filter_type]

    unique_types = sorted(list(set(t['type'] for t in training_programs)))

    context = {
        'recommendations': training_programs,
        'unique_types': unique_types,
        'current_type': filter_type,
        'search_query': search_query,
    }
    
    return render(request, 'core/recommendations.html', context)


@login_required
def instructorProfile(request):
    user = request.user
    
    userLogin = user.userlogin_set.select_related('instructor').first()
    instructor = userLogin.instructor if userLogin else None

    isDeptHead = user.roles.filter(name='deptHead').exists()

    profile_form = InstructorProfileForm(instance=user)
    password_form = PasswordChangeForm(user=user)

    if request.method == 'POST':
        if 'update_profile' in request.POST:
            profile_form = InstructorProfileForm(request.POST, request.FILES, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Your profile has been updated!")
                return redirect('instructorProfile')
        
        elif 'change_password' in request.POST:
            password_form = PasswordChangeForm(user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  
                messages.success(request, "Your password was successfully updated!")
                return redirect('instructorProfile')

    context = {
        'profile_form': profile_form,
        'password_form': password_form,
        'instructor': instructor,
        'isDeptHead': isDeptHead, 
    }
    
    return render(request, 'core/profile.html', context)