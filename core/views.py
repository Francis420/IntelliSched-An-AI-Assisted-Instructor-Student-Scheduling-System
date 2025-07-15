from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from scheduling.models import Subject
from authapi.views import has_role
from django.db import transaction
from core.models import User, Role, Instructor, Student, UserLogin


@login_required
@has_role('sysAdmin')
@has_role('deptHead')
def subjectList(request):
    subjects = Subject.objects.all().order_by('code')
    return render(request, 'core/subjects/list.html', {'subjects': subjects})


@login_required
@has_role('sysAdmin')
@has_role('deptHead')
def subjectCreate(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        name = request.POST.get('name')
        units = request.POST.get('units')
        defaultTerm = request.POST.get('defaultTerm')
        yearLevel = request.POST.get('yearLevel')
        durationMinutes = request.POST.get('durationMinutes')
        hasLabComponent = request.POST.get('hasLabComponent') == 'on'
        labDurationMinutes = request.POST.get('labDurationMinutes') or None
        preferredDeliveryMode = request.POST.get('preferredDeliveryMode')
        labDeliveryMode = request.POST.get('labDeliveryMode') or None
        requiredRoomType = request.POST.get('requiredRoomType') or ''
        requiredLabRoomType = request.POST.get('requiredLabRoomType') or ''
        notes = request.POST.get('notes') or ''

        if Subject.objects.filter(code=code).exists():
            messages.error(request, 'Subject with this code already exists.')
        else:
            Subject.objects.create(
                code=code,
                name=name,
                units=units,
                defaultTerm=defaultTerm,
                yearLevel=yearLevel,
                durationMinutes=durationMinutes,
                hasLabComponent=hasLabComponent,
                labDurationMinutes=labDurationMinutes,
                preferredDeliveryMode=preferredDeliveryMode,
                labDeliveryMode=labDeliveryMode,
                requiredRoomType=requiredRoomType,
                requiredLabRoomType=requiredLabRoomType,
                notes=notes
            )
            messages.success(request, 'Subject created successfully.')
            return redirect('subjectList')

    return render(request, 'core/subjects/create.html')



@login_required
@has_role('sysAdmin')
@has_role('deptHead')
def subjectUpdate(request, subjectCode):
    subject = get_object_or_404(Subject, code=subjectCode)

    if request.method == 'POST':
        subject.name = request.POST.get('name')
        subject.units = int(request.POST.get('units'))
        subject.defaultTerm = request.POST.get('defaultTerm')
        subject.yearLevel = request.POST.get('yearLevel')
        subject.durationMinutes = int(request.POST.get('durationMinutes'))

        subject.hasLabComponent = 'hasLabComponent' in request.POST
        subject.labDurationMinutes = request.POST.get('labDurationMinutes') or None
        subject.labDurationMinutes = int(subject.labDurationMinutes) if subject.labDurationMinutes else None

        subject.preferredDeliveryMode = request.POST.get('preferredDeliveryMode')
        subject.labDeliveryMode = request.POST.get('labDeliveryMode') or None
        subject.requiredRoomType = request.POST.get('requiredRoomType') or None
        subject.requiredLabRoomType = request.POST.get('requiredLabRoomType') or None
        subject.notes = request.POST.get('notes') or None

        subject.save()
        messages.success(request, 'Subject updated successfully.')
        return redirect('subjectList')

    return render(request, 'core/subjects/update.html', {'subject': subject})



@login_required
@has_role('sysAdmin')
@has_role('deptHead')
def subjectDelete(request, subjectCode):
    subject = get_object_or_404(Subject, code=subjectCode)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, 'Subject deleted.')
        return redirect('subjectList')
    return render(request, 'core/subjects/delete.html', {'subject': subject})



# ---------- Account Management ----------
@login_required
@has_role('sysAdmin')
@has_role('deptHead')
def userList(request):
    users = User.objects.prefetch_related('roles').all()
    return render(request, 'core/users/list.html', {'users': users})

@login_required
@has_role('sysAdmin')
@has_role('deptHead')
@transaction.atomic
def userCreate(request):
    roles = Role.objects.all()
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        firstName = request.POST.get('firstName')
        lastName = request.POST.get('lastName')
        middleInitial = request.POST.get('middleInitial')
        selected_roles = request.POST.getlist('roles')
        instructorId = request.POST.get('instructorId') or None
        studentId = request.POST.get('studentId') or None

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                firstName=firstName,
                lastName=lastName,
                middleInitial=middleInitial
            )

            user.roles.set(Role.objects.filter(id__in=selected_roles))

            instructor = Instructor.objects.filter(instructorId=instructorId).first() if instructorId else None
            student = Student.objects.filter(studentId=studentId).first() if studentId else None

            UserLogin.objects.create(user=user, instructor=instructor, student=student)
            messages.success(request, 'User created successfully.')
            return redirect('userList')

    return render(request, 'core/users/create.html', {'roles': roles})

@login_required
@has_role('sysAdmin')
@has_role('deptHead')
def userUpdate(request, userId):
    user = get_object_or_404(User, userId=userId)
    roles = Role.objects.all()
    login_info = UserLogin.objects.filter(user=user).first()

    if request.method == 'POST':
        user.firstName = request.POST.get('firstName')
        user.lastName = request.POST.get('lastName')
        user.middleInitial = request.POST.get('middleInitial')
        user.email = request.POST.get('email')
        selected_roles = request.POST.getlist('roles')

        user.roles.set(Role.objects.filter(id__in=selected_roles))
        user.save()

        instructorId = request.POST.get('instructorId') or None
        studentId = request.POST.get('studentId') or None

        if login_info:
            login_info.instructor = Instructor.objects.filter(instructorId=instructorId).first() if instructorId else None
            login_info.student = Student.objects.filter(studentId=studentId).first() if studentId else None
            login_info.save()
        else:
            UserLogin.objects.create(
                user=user,
                instructor=Instructor.objects.filter(instructorId=instructorId).first() if instructorId else None,
                student=Student.objects.filter(studentId=studentId).first() if studentId else None
            )

        messages.success(request, 'User updated successfully.')
        return redirect('userList')

    return render(request, 'core/users/update.html', {
        'userObj': user,
        'roles': roles,
        'login_info': login_info,
    })

@login_required
@has_role('sysAdmin')
@has_role('deptHead')
def userDelete(request, userId):
    user = get_object_or_404(User, userId=userId)
    if request.method == 'POST':
        user.delete()
        messages.success(request, 'User deleted successfully.')
        return redirect('userList')
    return render(request, 'core/users/delete.html', {'userObj': user})

