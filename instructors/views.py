from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from instructors.models import (
    InstructorExperience, 
    InstructorAvailability, 
    InstructorCredentials, 
    InstructorSubjectPreference,
    TeachingHistory,
)
from core.models import UserLogin
from scheduling.models import Semester
from authapi.views import has_role
from django.utils.timezone import now
from scheduling.models import Subject
from django.utils.dateparse import parse_time


# ---------- Instructor Experience ----------
@login_required
@has_role('instructor')
def experienceList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    experiences = InstructorExperience.objects.filter(
        instructor=instructor
    ).prefetch_related('relatedSubjects').order_by('-startDate')

    return render(request, 'instructors/experiences/list.html', {
        'experiences': experiences
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
        return redirect('experienceList')

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
        return redirect('experienceList')

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

    instructor = login.instructor
    experience = get_object_or_404(InstructorExperience, pk=experienceId, instructor=instructor)

    if request.method == 'POST':
        experience.delete()
        messages.success(request, 'Experience deleted.')
        return redirect('experienceList')

    return render(request, 'instructors/experiences/delete.html', {'experience': experience})



# ---------- Instructor Availability ----------
@login_required
@has_role('instructor')
def availabilityList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    availabilities = InstructorAvailability.objects.filter(instructor=instructor).order_by('dayOfWeek', 'startTime')
    return render(request, 'instructors/availability/list.html', {'availabilities': availabilities})


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
        return redirect('availabilityList')

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
        return redirect('availabilityList')

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
    return redirect('availabilityList')



# ---------- Instructor Credential ----------
@login_required
@has_role('instructor')
def credentialList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    instructor = login.instructor
    credentials = InstructorCredentials.objects.filter(instructor=instructor).order_by('-dateEarned')
    return render(request, 'instructors/credentials/list.html', {'credentials': credentials})


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
        relatedSubjectIds = request.POST.getlist('relatedSubjects')  # ✅ this is valid in view
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
        return redirect('credentialList')

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
        return redirect('credentialList')

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
    return redirect('credentialList')

# ---------- Instructor Preferences ----------
@login_required
@has_role('instructor')
def preferenceList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    preferences = InstructorSubjectPreference.objects.filter(instructor=login.instructor)
    return render(request, 'instructors/preferences/list.html', {'preferences': preferences})


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
        return redirect('preferenceList')

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
        return redirect('preferenceList')

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
        return redirect('preferenceList')

    return render(request, 'instructors/preferences/delete.html', {'preference': preference})



# ---------- Instructor Teaching History ----------
@login_required
@has_role('instructor')
def teachingHistoryList(request):
    login = UserLogin.objects.filter(user=request.user).first()
    if not login or not login.instructor:
        messages.error(request, "Instructor account not found.")
        return redirect('home')

    histories = TeachingHistory.objects.filter(instructor=login.instructor).select_related('subject', 'semester').order_by('-createdAt')
    return render(request, 'instructors/teachingHistory/list.html', {'histories': histories})


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
        return redirect('teachingHistoryList')

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
        history.save()
        messages.success(request, "Teaching history updated successfully.")
        return redirect('teachingHistoryList')

    return render(request, 'instructors/teachingHistory/update.html', {'history': history})


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
    return redirect('teachingHistoryList')


