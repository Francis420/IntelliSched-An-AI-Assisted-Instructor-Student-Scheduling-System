from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from rest_framework.authtoken.models import Token
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import api_view
from rest_framework.response import Response
from core.models import User

# Login page
def loginView(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            Token.objects.get_or_create(user=user)
            role = user.role

            if role == 'student':
                return redirect('/students/dashboard/')
            elif role == 'instructor':
                return redirect('/instructors/dashboard/')
            elif role == 'deptHead':
                return redirect('/department/dashboard/')
            else:
                return redirect('/admin/')
        else:
            return render(request, 'authapi/login.html', {'error': 'Invalid credentials'})

    return render(request, 'authapi/login.html')


# Logout view
def logoutView(request):
    logout(request)
    return redirect('login')


# DRF user info endpoint
@api_view(['GET'])
def userInfo(request):
    if request.user.is_authenticated:
        return Response({
            'userId': request.user.userId,
            'username': request.user.username,
            'email': request.user.email,
            'role': request.user.role,
            'firstName': request.user.firstName,
            'lastName': request.user.lastName,
        })
    return Response({'error': 'Not authenticated'}, status=401)
