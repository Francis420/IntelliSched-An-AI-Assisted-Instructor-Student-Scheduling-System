from django.shortcuts import render, redirect
from django.contrib.auth import authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from rest_framework.authtoken.models import Token
from django.core.exceptions import PermissionDenied
from functools import wraps
from core.models import User
from django.contrib.auth import authenticate, login 

def has_role(required_role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied()

            if user.roles.filter(name=required_role).exists():
                return view_func(request, *args, **kwargs)
            raise PermissionDenied()
        return _wrapped_view
    return decorator

def loginView(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)

            token, _ = Token.objects.get_or_create(user=user)
            request.session['token'] = token.key
            request.session['user_id'] = user.userId

            roles = user.roles.all()

            preferred_order = ['deptHead', 'instructor', 'student']
            sorted_roles = sorted(
                roles, key=lambda r: preferred_order.index(r.name) if r.name in preferred_order else 99
            )

            if not sorted_roles:
                messages.error(request, 'No roles assigned to this account.')
                return redirect('login')

            selected_role = sorted_roles[0].name
            request.session['role'] = selected_role

            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)

            if selected_role == 'deptHead':
                return redirect('deptHeadDashboard')
            elif selected_role == 'instructor':
                return redirect('instructorDashboard')
            elif selected_role == 'student':
                return redirect('studentDashboard')

        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'authapi/login.html')



def logoutView(request):
    token_key = request.session.get('token')
    if token_key:
        Token.objects.filter(key=token_key).delete()

    request.session.flush()
    return redirect('login')



@login_required
@has_role('deptHead')
def deptHeadDashboard(request):
    return render(request, 'dashboards/deptheadDashboard.html')


@login_required
@has_role('instructor')
def instructorDashboard(request):
    return render(request, 'dashboards/instructorDashboard.html')


@login_required
@has_role('student')
def studentDashboard(request):
    return render(request, 'dashboards/studentDashboard.html')
