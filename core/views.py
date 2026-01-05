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
    Advanced recommendation system for assigning instructors to subjects.
    Scores candidates based on:
    1. Credentials (related to subject)
    2. Combined Teaching History (Legacy + System Automation)
    3. Professional Experience (Weighted by Type & Employment Status)
    4. Recency & Rank
    """
    subject_id = request.GET.get("subject_id")
    
    # OPTIMIZATION: Prefetch all related data to avoid hitting the DB inside the loop
    instructors = Instructor.objects.filter(
        userlogin__user__isActive=True
    ).select_related('rank').prefetch_related(
        'credentials',
        'credentials__relatedSubjects',
        'experiences',
        'experiences__relatedSubjects',
        'legacy_experiences',    # For manual history
        'system_assignments'     # For automated history
    ).distinct()

    if not subject_id:
        return render(request, "core/recommendations.html", {
            "instructors": [], 
            "subjects": Subject.objects.all()
        })

    target_subject = get_object_or_404(Subject, subjectId=subject_id)
    recommendations = []

    # --- WEIGHTS CONFIGURATION ---
    WEIGHT_CREDENTIAL_MATCH = 20  
    WEIGHT_PAST_TEACHING = 15     
    WEIGHT_EXP_TEACHING = 3.0     # Per year for Academic roles
    WEIGHT_EXP_INDUSTRY = 2.0     # Per year for Industry/Research
    WEIGHT_EXP_GENERIC = 0.5      
    BONUS_RECENCY = 5             
    
    # Employment Status Multipliers (FTE)
    FTE_MULTIPLIER = {
        'FT': 1.0,  # Full Time
        'PT': 0.5,  # Part Time
        'CT': 0.75, # Contractual
    }

    BONUS_RANK = {                
        'Professor': 10,
        'Associate Professor': 8,
        'Assistant Professor': 6,
        'Instructor': 2,
    }

    current_year = date.today().year

    for inst in instructors:
        score = 0
        breakdown = [] 

        # ---------------------------------------------------------
        # 1. Credentials Score (Direct Subject Match)
        # ---------------------------------------------------------
        # Check if credential tags this subject in 'relatedSubjects'
        relevant_creds = [c for c in inst.credentials.all() if target_subject in c.relatedSubjects.all()]
        count_creds = len(relevant_creds)
        
        if count_creds > 0:
            points = count_creds * WEIGHT_CREDENTIAL_MATCH
            score += points
            breakdown.append(f"+{points} pts: {count_creds} relevant credential(s)")

        # ---------------------------------------------------------
        # 2. Combined Teaching History (Legacy + System)
        # ---------------------------------------------------------
        # A. Legacy Data (Manual Entry)
        legacy_entry = next((l for l in inst.legacy_experiences.all() if l.subject_id == target_subject.subjectId), None)
        legacy_count = legacy_entry.priorTimesTaught if legacy_entry else 0
        
        # B. System Data (Automated via TeachingAssignment)
        # Count how many times this instructor appears in the system history for this subject
        system_count = len([a for a in inst.system_assignments.all() if a.subject_id == target_subject.subjectId])
        
        total_taught = legacy_count + system_count
        
        if total_taught > 0:
            points = total_taught * WEIGHT_PAST_TEACHING
            score += points
            breakdown.append(f"+{points} pts: Taught {total_taught} times (Legacy: {legacy_count}, System: {system_count})")

        # ---------------------------------------------------------
        # 3. Weighted Professional Experience
        # ---------------------------------------------------------
        for exp in inst.experiences.all():
            # A. Calculate Duration
            start = exp.startDate.year
            # Use 'isCurrent' flag for end date
            if exp.isCurrent:
                end = current_year
            else:
                end = exp.endDate.year if exp.endDate else current_year
                
            duration = max(0, (end - start) + 1) # Min 1 year if same year

            # B. Determine Relevance
            # Check if subject is linked M2M OR if title/desc contains subject name
            is_relevant = False
            if target_subject in exp.relatedSubjects.all():
                is_relevant = True
            elif target_subject.name.lower() in exp.title.lower() or target_subject.name.lower() in exp.description.lower():
                is_relevant = True

            # C. Determine Weight based on New Categories
            weight = WEIGHT_EXP_GENERIC
            
            # 'Academic Position' is high value (Pedagogy)
            if exp.experienceType == 'Academic Position':
                # We give full points for relevant academic exp, slightly less for generic
                weight = WEIGHT_EXP_TEACHING if is_relevant else (WEIGHT_EXP_TEACHING * 0.5)
            
            # 'Industry', 'Research', 'Consultancy' only counts if relevant
            elif exp.experienceType in ['Industry', 'Research Role', 'Consultancy'] and is_relevant:
                weight = WEIGHT_EXP_INDUSTRY
            
            # 'Administrative' gets generic score
            elif exp.experienceType == 'Administrative Role':
                weight = WEIGHT_EXP_GENERIC

            # D. Apply FTE Multiplier (Full Time vs Part Time)
            fte = FTE_MULTIPLIER.get(exp.employmentType, 1.0)

            # Calculate
            exp_points = duration * weight * fte
            
            if exp_points > 0:
                score += exp_points
                # Only add Recency Bonus if the experience is relevant/academic and recent (last 3 years)
                if end >= (current_year - 3) and (is_relevant or exp.experienceType == 'Academic Position'):
                    score += BONUS_RECENCY

        # ---------------------------------------------------------
        # 4. Rank Bonus
        # ---------------------------------------------------------
        rank_name = inst.rank.name if inst.rank else "N/A"
        rank_points = BONUS_RANK.get(rank_name, 0)
        if rank_points > 0:
            score += rank_points

        # Final Object
        recommendations.append({
            "instructor": inst,
            "score": round(score, 1),
            "rank": rank_name,
            "match_details": breakdown,
            "past_teaching_count": total_taught
        })

    # Sort by Score Descending
    recommendations.sort(key=lambda x: x['score'], reverse=True)

    return render(request, "core/recommendations.html", {
        "target_subject": target_subject,
        "recommendations": recommendations,
        "subjects": Subject.objects.all()
    })


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