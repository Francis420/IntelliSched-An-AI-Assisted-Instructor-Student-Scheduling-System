from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from rest_framework.authtoken.models import Token
from django.core.exceptions import PermissionDenied
from functools import wraps
from core.models import User, UserLogin
from django.urls import reverse

from django.contrib.auth import authenticate, login 
from instructors.models import InstructorExperience, InstructorCredentials, InstructorAvailability, InstructorSubjectPreference, TeachingHistory
from itertools import chain
from operator import attrgetter

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
    return render(request, 'dashboards/deptHeadDashboard.html')


@login_required
@has_role('instructor')
def instructorDashboard(request):
    user_login = get_object_or_404(UserLogin, user=request.user)

    if not user_login.instructor:
        return render(request, 'dashboards/instructorDashboard.html', {
            "error": "Instructor profile not found."
        })

    instructor = user_login.instructor

    # Counts for overview cards
    experience_count = InstructorExperience.objects.filter(instructor=instructor).count()
    credential_count = InstructorCredentials.objects.filter(instructor=instructor).count()
    availability_count = InstructorAvailability.objects.filter(instructor=instructor).count()
    preference_count = InstructorSubjectPreference.objects.filter(instructor=instructor).count()
    teaching_history_count = TeachingHistory.objects.filter(instructor=instructor).count()

    # Get latest updates from each model
    experiences = InstructorExperience.objects.filter(instructor=instructor).order_by('-createdAt')[:3]
    credentials = InstructorCredentials.objects.filter(instructor=instructor).order_by('-createdAt')[:3]
    availabilities = InstructorAvailability.objects.filter(instructor=instructor).order_by('-createdAt')[:3]
    preferences = InstructorSubjectPreference.objects.filter(instructor=instructor).order_by('-createdAt')[:3]
    teaching_history = TeachingHistory.objects.filter(instructor=instructor).order_by('-createdAt')[:3]

    # Combine & sort all recent activities
    recent_activities = sorted(
        chain(experiences, credentials, availabilities, preferences, teaching_history),
        key=attrgetter("createdAt"),
        reverse=True
    )[:5]

    # Normalize with edit URLs
    activity_feed = []
    for item in recent_activities:
        if isinstance(item, InstructorExperience):
            url = reverse('experienceUpdate', args=[item.pk])
            label = "Experience"
        elif isinstance(item, InstructorCredentials):
            url = reverse('credentialUpdate', args=[item.pk])
            label = "Credential"
        elif isinstance(item, InstructorAvailability):
            url = reverse('availabilityUpdate', args=[item.pk])
            label = "Availability"
        elif isinstance(item, InstructorSubjectPreference):
            url = reverse('preferenceUpdate', args=[item.pk])
            label = "Preference"
        elif isinstance(item, TeachingHistory):
            url = reverse('teachingHistoryUpdate', args=[item.pk])
            label = "Teaching History"
        else:
            url = None
            label = "Update"

        activity_feed.append({
            "title": f"{label}: {getattr(item, 'title', getattr(item, 'name', 'Update'))}",
            "description": getattr(item, "description", getattr(item, "details", "")),
            "timestamp": item.createdAt,
            "url": url,
        })

    context = {
        "instructor": instructor,
        "experience_count": experience_count,
        "credential_count": credential_count,
        "availability_count": availability_count,
        "preference_count": preference_count,
        "teaching_history_count": teaching_history_count,
        "recent_activities": activity_feed,
    }
    return render(request, 'dashboards/instructorDashboard.html', context)


@login_required
@has_role('student')
def studentDashboard(request):
    return render(request, 'dashboards/studentDashboard.html')
