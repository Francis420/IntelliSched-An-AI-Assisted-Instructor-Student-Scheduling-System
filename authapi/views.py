from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from rest_framework.authtoken.models import Token
from django.core.exceptions import PermissionDenied
from functools import wraps
from core.models import User, UserLogin, Role, Instructor
from django.urls import reverse
from django.contrib.auth import authenticate, login 
from instructors.models import InstructorExperience, InstructorCredentials
from itertools import chain
from operator import attrgetter
from scheduling.models import Curriculum, Semester, Subject, Room
from aimatching.models import MatchingRun
from operator import itemgetter


def has_role(required_role):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied()
            
            if user.is_superuser:
                return view_func(request, *args, **kwargs)

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

            preferred_order = ['deptHead', 'instructor']
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
                return redirect('recommendInstructors')
            elif selected_role == 'instructor':
                return redirect('instructorDashboard')

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
    # Counts for cards
    curriculum_count = Curriculum.objects.count()
    semester_count = Semester.objects.count()
    subject_count = Subject.objects.count()
    instructor_count = Instructor.objects.count()
    room_count = Room.objects.count()
    matching_runs = MatchingRun.objects.count()

    # Recent activities: normalize timestamp key
    activities = []

    for obj in Curriculum.objects.order_by('-createdAt')[:3]:
        activities.append({
            "title": f"Curriculum: {obj.name}",
            "description": obj.description or "Curriculum added/updated",
            "timestamp": obj.createdAt,
            "link": reverse("curriculumUpdate", args=[obj.curriculumId]),
        })

    for obj in Semester.objects.order_by('-createdAt')[:3]:
        activities.append({
            "title": f"Semester: {obj.name}",
            "description": f"Academic Year: {obj.academicYear}",
            "timestamp": obj.createdAt,
            "link": reverse("semesterUpdate", args=[obj.semesterId]),
        })

    for obj in Subject.objects.order_by('-createdAt')[:3]:
        activities.append({
            "title": f"Subject: {obj.name}",
            "description": obj.description or "Subject created/updated",
            "timestamp": obj.createdAt,
            "link": reverse("subjectUpdate", args=[obj.code]),
        })

    for obj in Room.objects.order_by('-createdAt')[:3]:
        activities.append({
            "title": f"Room: {obj.roomCode}",
            "description": f"Building: {obj.building}",
            "timestamp": obj.createdAt,
            "link": reverse("roomUpdate", args=[obj.roomId]),
        })

    for obj in MatchingRun.objects.order_by('-generatedAt')[:3]:
        activities.append({
            "title": f"AI Matching Run ({obj.semester.name})",
            "description": f"{obj.totalSubjects} subjects, {obj.totalInstructors} instructors",
            "timestamp": obj.generatedAt,
            "link": reverse("matchingResults", args=[obj.batchId]),
        })

    # Sort everything by timestamp desc
    recent_activities = sorted(activities, key=itemgetter("timestamp"), reverse=True)[:5]

    context = {
        "curriculum_count": curriculum_count,
        "semester_count": semester_count,
        "subject_count": subject_count,
        "instructor_count": instructor_count,
        "room_count": room_count,
        "matching_runs": matching_runs,
        "recent_activities": recent_activities,
    }
    return render(request, "dashboards/deptHeadDashboard.html", context)


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

    # Get latest updates from each model
    experiences = InstructorExperience.objects.filter(instructor=instructor).order_by('-createdAt')[:3]
    credentials = InstructorCredentials.objects.filter(instructor=instructor).order_by('-createdAt')[:3]



    # Combine & sort all recent activities
    recent_activities = sorted(
        chain(experiences, credentials),
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
        "recent_activities": activity_feed,
    }
    return render(request, 'dashboards/instructorDashboard.html', context)
