from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from core.models import User, Role, Student, UserLogin

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
