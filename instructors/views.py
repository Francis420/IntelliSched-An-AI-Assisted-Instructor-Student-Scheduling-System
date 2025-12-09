from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from instructors.models import (
    InstructorExperience, 
    InstructorAvailability, 
    InstructorCredentials, 
    InstructorSubjectPreference,
    TeachingHistory,
    InstructorRank,
    InstructorDesignation,
    InstructorAcademicAttainment,
)
from core.models import UserLogin
from scheduling.models import Semester
from authapi.views import has_role
from django.utils.timezone import now
from scheduling.models import Subject
from django.utils.dateparse import parse_time
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import Q

# ---------- Instructor Dashboard ----------
@login_required
@has_role('instructor')
def instructorDashboard(request):
    return render(request, 'instructors/dashboard.html')


# ---------- Instructor Experience ----------
@login_required
@has_role('instructor')
def experienceList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    experiences = InstructorExperience.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-startDate")

    if query:
        experiences = experiences.filter(
            Q(title__icontains=query) |
            Q(organization__icontains=query) |
            Q(description__icontains=query) |
            Q(experienceType__icontains=query) |
            Q(relatedSubjects__name__icontains=query) |
            Q(relatedSubjects__code__icontains=query)
        ).distinct()

    paginator = Paginator(experiences, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/experiences/list.html", {
        "experiences": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def experienceListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    experiences = InstructorExperience.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-startDate")

    if query:
        experiences = experiences.filter(
            Q(title__icontains=query) |
            Q(organization__icontains=query) |
            Q(description__icontains=query) |
            Q(experienceType__icontains=query) |
            Q(relatedSubjects__name__icontains=query) |
            Q(relatedSubjects__code__icontains=query)
        ).distinct()

    paginator = Paginator(experiences, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/experiences/_table.html", {
        "experiences": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('instructor')
def experienceCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor

    if request.method == 'POST':
        title = request.POST.get('title')
        organization = request.POST.get('organization')
        startDate = request.POST.get('startDate')
        endDate = request.POST.get('endDate') or None
        description = request.POST.get('description')
        experienceType = request.POST.get('experienceType')
        relatedSubjectIds = list(map(int, request.POST.getlist('relatedSubjects')))

        experience = InstructorExperience.objects.create(
            instructor=instructor,
            title=title,
            organization=organization,
            startDate=startDate,
            endDate=endDate,
            description=description,
            experienceType=experienceType
        )
        if relatedSubjectIds:
            experience.relatedSubjects.set(relatedSubjectIds)

        messages.success(request, 'Experience added successfully.')
        return redirect('instructorDashboard')

    subjects = Subject.objects.all()
    return render(request, 'instructors/experiences/create.html', {'subjects': subjects})


@login_required
@has_role('instructor')
def experienceUpdate(request, experienceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    experience = get_object_or_404(InstructorExperience, pk=experienceId, instructor=instructor)

    if request.method == 'POST':
        experience.title = request.POST.get('title')
        experience.organization = request.POST.get('organization')
        experience.startDate = request.POST.get('startDate')
        experience.endDate = request.POST.get('endDate') or None
        experience.description = request.POST.get('description')
        experience.experienceType = request.POST.get('type')
        relatedSubjectIds = list(map(int, request.POST.getlist('relatedSubjects')))

        experience.save()
        experience.relatedSubjects.set(relatedSubjectIds)

        messages.success(request, 'Experience updated successfully.')
        return redirect('instructorDashboard')

    subjects = Subject.objects.all()
    return render(request, 'instructors/experiences/update.html', {
        'experience': experience,
        'subjects': subjects
    })


@login_required
@has_role('instructor')
def experienceDelete(request, experienceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    experience = get_object_or_404(InstructorExperience, pk=experienceId, instructor=login.instructor)
    experience.delete()
    messages.success(request, "Experience deleted successfully.")
    return redirect('instructorDashboard')



# ---------- Instructor Availability ----------
@login_required
@has_role('instructor')
def availabilityList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    availabilities = InstructorAvailability.objects.filter(instructor=instructor)

    if query:
        availabilities = availabilities.filter(
            Q(dayOfWeek__icontains=query) |
            Q(startTime__icontains=query) |
            Q(endTime__icontains=query)
        )

    paginator = Paginator(availabilities, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/availability/list.html", {
        "availabilities": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def availabilityListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    availabilities = InstructorAvailability.objects.filter(instructor=instructor)

    if query:
        availabilities = availabilities.filter(
            Q(dayOfWeek__icontains=query) |
            Q(startTime__icontains=query) |
            Q(endTime__icontains=query)
        )

    paginator = Paginator(availabilities, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/availability/_cards.html", {
        "availabilities": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('instructor')
def availabilityCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    if request.method == 'POST':
        dayOfWeek = request.POST.get('dayOfWeek')
        startTime = request.POST.get('startTime')
        endTime = request.POST.get('endTime')

        InstructorAvailability.objects.create(
            instructor=instructor,
            dayOfWeek=dayOfWeek,
            startTime=startTime,
            endTime=endTime
        )
        messages.success(request, 'Availability added successfully.')
        return redirect('instructorDashboard')

    return render(request, 'instructors/availability/create.html', {'days': days})


DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
@login_required
@has_role('instructor')
def availabilityUpdate(request, availabilityId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    availability = get_object_or_404(InstructorAvailability, pk=availabilityId, instructor=login.instructor)

    if request.method == 'POST':
        availability.dayOfWeek = request.POST.get('dayOfWeek')
        availability.startTime = parse_time(request.POST.get('startTime'))
        availability.endTime = parse_time(request.POST.get('endTime'))
        availability.save()

        messages.success(request, "Availability updated successfully.")
        return redirect('instructorDashboard')

    return render(request, 'instructors/availability/update.html', {
        'availability': availability,
        'days': DAYS_OF_WEEK,
        })


@login_required
@has_role('instructor')
def availabilityDelete(request, availabilityId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    availability = get_object_or_404(InstructorAvailability, pk=availabilityId, instructor=login.instructor)
    availability.delete()
    messages.success(request, "Availability deleted successfully.")
    return redirect('instructorDashboard')



# ---------- Instructor Credential ----------
@login_required
@has_role('instructor')
def credentialList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    credentials = InstructorCredentials.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-dateEarned")

    if query:
        credentials = credentials.filter(
            Q(title__icontains=query) |
            Q(type__icontains=query) |
            Q(description__icontains=query) |
            Q(issuer__icontains=query) |
            Q(relatedSubjects__code__icontains=query) |
            Q(relatedSubjects__name__icontains=query)
        ).distinct()

    paginator = Paginator(credentials, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/credentials/list.html", {
        "credentials": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def credentialListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    credentials = InstructorCredentials.objects.filter(
        instructor=instructor
    ).prefetch_related("relatedSubjects").order_by("-dateEarned")

    if query:
        credentials = credentials.filter(
            Q(title__icontains=query) |
            Q(type__icontains=query) |
            Q(description__icontains=query) |
            Q(issuer__icontains=query) |
            Q(relatedSubjects__code__icontains=query) |
            Q(relatedSubjects__name__icontains=query)
        ).distinct()

    paginator = Paginator(credentials, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/credentials/_table.html", {
        "credentials": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('instructor')
def credentialCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    subjects = Subject.objects.all()
    types = ['Certification', 'Workshop', 'Training', 'License']

    if request.method == 'POST':
        type = request.POST.get('type')
        title = request.POST.get('title')
        description = request.POST.get('description')
        relatedSubjectIds = request.POST.getlist('relatedSubjects')
        isVerified = request.POST.get('isVerified') == 'on'
        documentUrl = request.POST.get('documentUrl')
        dateEarned = request.POST.get('dateEarned')

        credential = InstructorCredentials.objects.create(
            instructor=instructor,
            type=type,
            title=title,
            description=description,
            isVerified=isVerified,
            documentUrl=documentUrl,
            dateEarned=dateEarned
        )
        credential.relatedSubjects.set(relatedSubjectIds)

        messages.success(request, "Credential added successfully.")
        return redirect('instructorDashboard')

    return render(request, 'instructors/credentials/create.html', {
        'types': types,
        'subjects': subjects
    })


@login_required
@has_role('instructor')
def credentialUpdate(request, credentialId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    credential = get_object_or_404(InstructorCredentials, pk=credentialId, instructor=login.instructor)
    subjects = Subject.objects.all()
    types = ['Certification', 'Workshop', 'Training', 'License']

    if request.method == 'POST':
        credential.type = request.POST.get('type')
        credential.title = request.POST.get('title')
        credential.description = request.POST.get('description')
        credential.isVerified = request.POST.get('isVerified') == 'on'
        credential.documentUrl = request.POST.get('documentUrl')
        credential.dateEarned = request.POST.get('dateEarned')
        credential.relatedSubjects.set(request.POST.getlist('relatedSubjects'))
        credential.save()

        messages.success(request, "Credential updated successfully.")
        return redirect('instructorDashboard')

    return render(request, 'instructors/credentials/update.html', {
        'credential': credential,
        'types': types,
        'subjects': subjects
    })


@login_required
@has_role('instructor')
def credentialDelete(request, credentialId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    credential = get_object_or_404(InstructorCredentials, pk=credentialId, instructor=login.instructor)
    credential.delete()
    messages.success(request, "Credential deleted successfully.")
    return redirect('instructorDashboard')


# ---------- Instructor Preferences ----------
@login_required
@has_role('instructor')
def preferenceList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    preferences = InstructorSubjectPreference.objects.filter(
        instructor=instructor
    ).select_related("subject").order_by("subject__code")

    if query:
        preferences = preferences.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(preferenceType__icontains=query) |
            Q(reason__icontains=query)
        )

    paginator = Paginator(preferences, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/preferences/list.html", {
        "preferences": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def preferenceListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    preferences = InstructorSubjectPreference.objects.filter(
        instructor=instructor
    ).select_related("subject").order_by("subject__code")

    if query:
        preferences = preferences.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(preferenceType__icontains=query) |
            Q(reason__icontains=query)
        )

    paginator = Paginator(preferences, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/preferences/_table.html", {
        "preferences": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })



@login_required
@has_role('instructor')
def preferenceCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    subjects = Subject.objects.all()
    types = ['Prefer', 'Neutral', 'Avoid']

    if request.method == 'POST':
        subjectId = request.POST.get('subject')
        subject = get_object_or_404(Subject, pk=subjectId)
        preferenceType = request.POST.get('preferenceType')
        reason = request.POST.get('reason')

        InstructorSubjectPreference.objects.create(
            instructor=login.instructor,
            subject=subject,
            preferenceType=preferenceType,
            reason=reason
        )
        messages.success(request, 'Preference added successfully.')
        return redirect('instructorDashboard')

    return render(request, 'instructors/preferences/create.html', {
        'subjects': subjects,
        'types': types
    })


@login_required
@has_role('instructor')
def preferenceUpdate(request, preferenceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    preference = get_object_or_404(InstructorSubjectPreference, pk=preferenceId, instructor=login.instructor)
    types = ['Prefer', 'Neutral', 'Avoid']

    if request.method == 'POST':
        preference.preferenceType = request.POST.get('preferenceType')
        preference.reason = request.POST.get('reason')
        preference.save()
        messages.success(request, 'Preference updated successfully.')
        return redirect('instructorDashboard')

    return render(request, 'instructors/preferences/update.html', {
        'preference': preference,
        'types': types
    })


@login_required
@has_role('instructor')
def preferenceDelete(request, preferenceId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    preference = get_object_or_404(InstructorSubjectPreference, pk=preferenceId, instructor=login.instructor)

    if request.method == 'POST':
        preference.delete()
        messages.success(request, 'Preference deleted successfully.')
        return redirect('instructorDashboard')

    return render(request, 'instructors/preferences/delete.html', {'preference': preference})



# ---------- Instructor Teaching History ----------
@login_required
@has_role('instructor')
def teachingHistoryList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    histories = TeachingHistory.objects.filter(
        instructor=instructor
    ).select_related("subject", "semester").order_by("-createdAt")

    if query:
        histories = histories.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(semester__name__icontains=query)
        )

    paginator = Paginator(histories, 5)
    page_obj = paginator.get_page(page)

    return render(request, "instructors/teachingHistory/list.html", {
        "histories": page_obj,
        "query": query,
    })


@login_required
@has_role('instructor')
def teachingHistoryListLive(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        return JsonResponse({"error": "Instructor not found"}, status=400)

    instructor = login.instructor
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    histories = TeachingHistory.objects.filter(
        instructor=instructor
    ).select_related("subject", "semester").order_by("-createdAt")

    if query:
        histories = histories.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(semester__name__icontains=query)
        )

    paginator = Paginator(histories, 5)
    page_obj = paginator.get_page(page)

    html = render_to_string("instructors/teachingHistory/_table.html", {
        "histories": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    })


@login_required
@has_role('instructor')
def teachingHistoryCreate(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    subjects = Subject.objects.all()
    semesters = Semester.objects.all()

    if request.method == 'POST':
        subjectId = request.POST.get('subject')
        semesterId = request.POST.get('semester')
        timesTaught = request.POST.get('timesTaught', 1)

        subject = get_object_or_404(Subject, pk=subjectId)
        semester = get_object_or_404(Semester, pk=semesterId)

        history, created = TeachingHistory.objects.get_or_create(
            instructor=login.instructor,
            subject=subject,
            semester=semester,
            defaults={'timesTaught': timesTaught}
        )

        if not created:
            messages.error(request, "Record already exists. Try updating it instead.")
        else:
            messages.success(request, "Teaching history added successfully.")
        return redirect('instructorDashboard')

    return render(request, 'instructors/teachingHistory/create.html', {
        'subjects': subjects,
        'semesters': semesters
    })


@login_required
@has_role('instructor')
def teachingHistoryUpdate(request, teachingId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    history = get_object_or_404(TeachingHistory, pk=teachingId, instructor=login.instructor)

    if request.method == 'POST':
        history.timesTaught = request.POST.get('timesTaught', 1)
        history.subject_id = request.POST.get('subject')
        history.semester_id = request.POST.get('semester')
        history.save()
        messages.success(request, "Teaching history updated successfully.")
        return redirect('instructorDashboard')

    subjects = Subject.objects.all()
    semesters = Semester.objects.all()

    return render(request, 'instructors/teachingHistory/update.html', {
        'history': history,
        'subjects': subjects,
        'semesters': semesters,
    })


@login_required
@has_role('instructor')
def teachingHistoryDelete(request, teachingId):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    history = get_object_or_404(TeachingHistory, pk=teachingId, instructor=login.instructor)
    history.delete()
    messages.success(request, "Teaching history deleted successfully.")
    return redirect('instructorDashboard')



# ---------- Instructor Rank Configuration ----------
@login_required
@has_role('deptHead') 
def instructorRankList(request):
    ranks = InstructorRank.objects.all()
    
    return render(request, "instructors/ranks/list.html", {"ranks": ranks})

@login_required
@has_role('deptHead')
def instructorRankCreate(request):
    if request.method == "POST":
        try:
            name = request.POST.get('name').strip()
            
            data = {
                'instructionHours': int(request.POST.get('instructionHours', 0)),
                'researchHours': int(request.POST.get('researchHours', 0)),
                'extensionHours': int(request.POST.get('extensionHours', 0)),
                'productionHours': int(request.POST.get('productionHours', 0)),
                'consultationHours': int(request.POST.get('consultationHours', 0)),
                'classAdviserHours': int(request.POST.get('classAdviserHours', 0)),
            }
            
            if not name:
                messages.error(request, "Rank name cannot be empty.")
                return redirect('instructorRankCreate')

            for key, value in data.items():
                if value < 0:
                    messages.error(request, f"Hours for {key} must be non-negative.")
                    return redirect('instructorRankCreate')
            
            InstructorRank.objects.create(
                name=name,
                **data
            )
            
            messages.success(request, f"Instructor Rank '{name}' created successfully.")
            return redirect('instructorRankList')
            
        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/ranks/create.html")

@login_required
@has_role('deptHead')
def instructorRankUpdate(request, rankId):
    rank = get_object_or_404(InstructorRank, pk=rankId)

    if request.method == "POST":
        try:
            rank.name = request.POST.get('name').strip()
            
            rank.instructionHours = int(request.POST.get('instructionHours', rank.instructionHours))
            rank.researchHours = int(request.POST.get('researchHours', rank.researchHours))
            rank.extensionHours = int(request.POST.get('extensionHours', rank.extensionHours))
            rank.productionHours = int(request.POST.get('productionHours', rank.productionHours))
            rank.consultationHours = int(request.POST.get('consultationHours', rank.consultationHours))
            rank.classAdviserHours = int(request.POST.get('classAdviserHours', rank.classAdviserHours))

            if not rank.name:
                messages.error(request, "Rank name cannot be empty.")
                # Fall through to render
            elif any(h < 0 for h in [rank.instructionHours, rank.researchHours, rank.extensionHours, rank.productionHours, rank.consultationHours, rank.classAdviserHours]):
                messages.error(request, "All hour fields must be non-negative.")
                # Fall through to render
            else:
                rank.save()
                messages.success(request, f"Instructor Rank '{rank.name}' updated successfully.")
                return redirect('instructorRankList')

        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/ranks/update.html", {"rank": rank})



# ---------- Instructor Designation Configuration ----------
@login_required
@has_role('deptHead') 
def instructorDesignationList(request):
    designations = InstructorDesignation.objects.all()
    
    return render(request, "instructors/designations/list.html", {
        "designations": designations,
    })

@login_required
@has_role('deptHead')
def instructorDesignationCreate(request):
    if request.method == "POST":
        try:
            name = request.POST.get('name').strip()
            
            # Retrieve all hour fields
            data = {
                'adminSupervisionHours': int(request.POST.get('adminSupervisionHours', 0)),
                'instructionHours': int(request.POST.get('instructionHours', 0)),
                'researchHours': int(request.POST.get('researchHours', 0)),
                'extensionHours': int(request.POST.get('extensionHours', 0)),
                'productionHours': int(request.POST.get('productionHours', 0)),
                'consultationHours': int(request.POST.get('consultationHours', 0)),
            }
            
            # Input validation
            if not name:
                messages.error(request, "Designation name cannot be empty.")
                return redirect('instructorDesignationCreate')

            for key, value in data.items():
                if value < 0:
                    messages.error(request, f"Hours for {key} must be non-negative.")
                    return redirect('instructorDesignationCreate')
            
            # Create the object
            InstructorDesignation.objects.create(
                name=name,
                **data
            )
            
            messages.success(request, f"Instructor Designation '{name}' created successfully.")
            return redirect('instructorDesignationList')
            
        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/designations/create.html")


@login_required
@has_role('deptHead')
def instructorDesignationUpdate(request, designationId):
    designation = get_object_or_404(InstructorDesignation, pk=designationId)

    if request.method == "POST":
        try:
            designation.name = request.POST.get('name').strip()
            
            # Retrieve and update all hour fields
            designation.adminSupervisionHours = int(request.POST.get('adminSupervisionHours', designation.adminSupervisionHours))
            designation.instructionHours = int(request.POST.get('instructionHours', designation.instructionHours))
            designation.researchHours = int(request.POST.get('researchHours', designation.researchHours))
            designation.extensionHours = int(request.POST.get('extensionHours', designation.extensionHours))
            designation.productionHours = int(request.POST.get('productionHours', designation.productionHours))
            designation.consultationHours = int(request.POST.get('consultationHours', designation.consultationHours))

            # Basic Validation
            if not designation.name:
                messages.error(request, "Designation name cannot be empty.")
            elif any(h < 0 for h in [designation.adminSupervisionHours, designation.instructionHours, designation.researchHours, designation.extensionHours, designation.productionHours, designation.consultationHours]):
                messages.error(request, "All hour fields must be non-negative.")
            else:
                designation.save()
                messages.success(request, f"Instructor Designation '{designation.name}' updated successfully.")
                return redirect('instructorDesignationList')

        except ValueError:
            messages.error(request, "Invalid number entered for one of the hour fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/designations/update.html", {
        "designation": designation,
    })


# ---------- Instructor Academic Attainment Configuration ----------
@login_required
@has_role('deptHead') 
def instructorAttainmentList(request):
    attainments = InstructorAcademicAttainment.objects.all()
    
    return render(request, "instructors/attainments/list.html", {
        "attainments": attainments,
    })

@login_required
@has_role('deptHead')
def instructorAttainmentCreate(request):
    if request.method == "POST":
        try:
            name = request.POST.get('name').strip()
            suffix = request.POST.get('suffix').strip()
            
            data = {
                'overloadUnitsHasDesignation': int(request.POST.get('overloadUnitsHasDesignation', 0)),
                'overloadUnitsNoDesignation': int(request.POST.get('overloadUnitsNoDesignation', 0)),
            }
            
            if not name:
                messages.error(request, "Attainment name cannot be empty.")
                return redirect('instructorAttainmentCreate')

            for key, value in data.items():
                if value < 0:
                    messages.error(request, f"Units must be non-negative.")
                    return redirect('instructorAttainmentCreate')
            
            InstructorAcademicAttainment.objects.create(
                name=name,
                suffix=suffix,
                **data
            )
            
            messages.success(request, f"Academic Attainment '{name}' created successfully.")
            return redirect('instructorAttainmentList')
            
        except ValueError:
            messages.error(request, "Invalid number entered for one of the unit fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/attainments/create.html")

@login_required
@has_role('deptHead')
def instructorAttainmentUpdate(request, attainmentId):
    attainment = get_object_or_404(InstructorAcademicAttainment, pk=attainmentId)

    if request.method == "POST":
        try:
            attainment.name = request.POST.get('name').strip()
            attainment.suffix = request.POST.get('suffix').strip()
            
            attainment.overloadUnitsHasDesignation = int(request.POST.get('overloadUnitsHasDesignation', attainment.overloadUnitsHasDesignation))
            attainment.overloadUnitsNoDesignation = int(request.POST.get('overloadUnitsNoDesignation', attainment.overloadUnitsNoDesignation))

            if not attainment.name:
                messages.error(request, "Attainment name cannot be empty.")
            elif attainment.overloadUnitsHasDesignation < 0 or attainment.overloadUnitsNoDesignation < 0:
                messages.error(request, "All unit fields must be non-negative.")
            else:
                attainment.save()
                messages.success(request, f"Academic Attainment '{attainment.name}' updated successfully.")
                return redirect('instructorAttainmentList')

        except ValueError:
            messages.error(request, "Invalid number entered for one of the unit fields.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")

    return render(request, "instructors/attainments/update.html", {
        "attainment": attainment,
    })
