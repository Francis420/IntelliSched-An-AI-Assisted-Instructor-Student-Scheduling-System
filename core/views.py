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
@login_required
@has_role('deptHead')
def recommendInstructors(request):
    """
    Advanced recommendation system for assigning instructors to subjects.
    Scores candidates based on:
    1. Relevance of Credentials (high weight)
    2. Teaching History with this specific subject (high weight)
    3. Weighted Professional Experience (Teaching > Research > Admin)
    4. Recency of Experience (bonus for current/recent roles)
    """
    subject_id = request.GET.get("subject_id")
    
    instructors = Instructor.objects.filter(
        userlogin__user__isActive=True
    ).select_related('rank').distinct()

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
    WEIGHT_EXP_TEACHING = 3.0     
    WEIGHT_EXP_INDUSTRY = 2.0     
    WEIGHT_EXP_GENERIC = 0.5      
    BONUS_RECENCY = 5             
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

        # 1. Credentials Score (Direct Subject Match)
        relevant_creds = inst.credentials.filter(relatedSubjects=target_subject).count()
        if relevant_creds > 0:
            points = relevant_creds * WEIGHT_CREDENTIAL_MATCH
            score += points
            breakdown.append(f"+{points} pts: {relevant_creds} relevant credential(s)")

        # 2. Teaching History 
        past_sections = InstructorLegacyExperience.objects.filter(
            instructor=inst, 
            subject=target_subject
        ).count()
        
        if past_sections > 0:
            points = past_sections * WEIGHT_PAST_TEACHING
            score += points
            breakdown.append(f"+{points} pts: Taught subject {past_sections} times")

        # 3. Weighted Professional Experience
        experiences = inst.experiences.all()
        
        for exp in experiences:
            # Calculate duration
            start = exp.startDate.year
            end = exp.endDate.year if exp.endDate else current_year
            duration = max(0, (end - start) + 1)

            # Determine relevance
            weight = WEIGHT_EXP_GENERIC
            is_relevant = False

            # Check if subject name appears in title/description or related subjects
            if (target_subject.name.lower() in exp.title.lower() or 
                target_subject.name.lower() in exp.description.lower() or
                target_subject in exp.relatedSubjects.all()):
                is_relevant = True
            
            # Apply Weights
            if exp.experienceType == 'Teaching Experience':
                weight = WEIGHT_EXP_TEACHING
            elif exp.experienceType in ['Work Experience', 'Research Role'] and is_relevant:
                weight = WEIGHT_EXP_INDUSTRY
            
            score += duration * weight
            
            # Recency Bonus
            if end >= (current_year - 3) and is_relevant:
                score += BONUS_RECENCY

        # 4. Rank Bonus
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
            "past_teaching_count": past_sections
        })

    # Sort by Score Descending
    recommendations.sort(key=lambda x: x['score'], reverse=True)

    return render(request, "core/recommendations.html", {
        "target_subject": target_subject,
        "recommendations": recommendations,
        "subjects": Subject.objects.all()
    })