from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from scheduling.models import (
    Subject, 
    Curriculum,
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
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_GET



# ---------- Home ----------
def home(request):
    return render(request, 'home.html')

# ---------- # Check if username/instructorId exists ----------
@require_GET
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


# ---------- Subjects ----------
def subjectList(request):
    curriculums = Curriculum.objects.order_by('-createdAt')
    
    curriculum_id = request.GET.get('curriculumId')

    if not curriculum_id and curriculums.exists():
        selected_curriculum = curriculums.first()
    else:
        selected_curriculum = get_object_or_404(Curriculum, pk=curriculum_id)

    subjects = Subject.objects.filter(curriculum=selected_curriculum)

    return render(request, 'core/subjects/list.html', {
        'subjects': subjects,
        'curriculums': curriculums,
        'selectedCurriculumId': selected_curriculum.curriculumId,
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
    instructor_logins = UserLogin.objects.select_related('user', 'instructor') \
        .filter(user__roles__name='instructor', instructor__isnull=False) \
        .distinct()

    context = {
        'instructorLogins': instructor_logins
    }
    return render(request, 'core/instructors/list.html', context)


@login_required
@has_role('deptHead')
@transaction.atomic
def instructorAccountCreate(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        firstName = request.POST.get('firstName')
        lastName = request.POST.get('lastName')
        instructorId = request.POST.get('instructorId')
        employmentType = request.POST.get('employmentType')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        elif Instructor.objects.filter(instructorId=instructorId).exists():
            messages.error(request, 'Instructor ID already exists.')
        else:
            # Create User
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                firstName=firstName,
                lastName=lastName,
                isActive=True
            )

            # Assign Role
            instructorRole = Role.objects.get(name='instructor')
            user.roles.add(instructorRole)

            # Create Instructor Profile
            instructor = Instructor.objects.create(
                instructorId=instructorId,
                employmentType=employmentType
            )

            # Link in UserLogin
            UserLogin.objects.create(user=user, instructor=instructor)

            messages.success(request, 'Instructor account sucessfully created.')
            return redirect('instructorAccountList')

    return render(request, 'core/instructors/create.html')



@login_required
@has_role('deptHead')
@transaction.atomic
def instructorAccountUpdate(request, userId):
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

        if newInstructorId and newInstructorId != instructor.instructorId:
            # Check uniqueness
            if Instructor.objects.filter(instructorId=newInstructorId).exclude(pk=instructor.pk).exists():
                messages.error(request, 'Instructor ID already exists.')
                return redirect('instructorAccountUpdate', userId=user.userId)
            instructor.instructorId = newInstructorId

        instructor.employmentType = employmentType
        instructor.save()

        messages.success(request, 'Instructor account updated successfully.')
        return redirect('instructorAccountList')

    return render(request, 'core/instructors/update.html', {
        'user': user,
        'instructor': instructor
    })


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
@login_required
def studentAccountList(request):
    student_logins = UserLogin.objects.select_related('user', 'student') \
        .filter(user__roles__name='student', student__isnull=False) \
        .distinct()

    context = {
        'studentLogins': student_logins
    }
    return render(request, 'core/students/list.html', context)

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

