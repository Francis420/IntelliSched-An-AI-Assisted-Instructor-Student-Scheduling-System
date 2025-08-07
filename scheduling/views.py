from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from authapi.views import has_role  
from scheduling.models import (
    Room, 
    GenEdSchedule, 
    Semester,
    Schedule,
    Curriculum,
    Section,
    SubjectOffering,
    Subject,
)
from core.models import (
    Student,
    UserLogin,
)
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import Q
import string
from django.urls import reverse



# ---------- Rooms ----------
@login_required
@has_role('deptHead')
def roomList(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    rooms = Room.objects.all().order_by("roomCode")

    if query:
        rooms = rooms.filter(
            Q(roomCode__icontains=query) |
            Q(building__icontains=query) |
            Q(type__icontains=query) |
            Q(notes__icontains=query)
        )

    paginator = Paginator(rooms, 10)
    page_obj = paginator.get_page(page)

    return render(request, "scheduling/rooms/list.html", {
        "rooms": page_obj,
        "query": query,
    })


@login_required
@has_role('deptHead')
def roomListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    rooms = Room.objects.all().order_by("roomCode")

    if query:
        rooms = rooms.filter(
            Q(roomCode__icontains=query) |
            Q(building__icontains=query) |
            Q(type__icontains=query) |
            Q(notes__icontains=query)
        )

    paginator = Paginator(rooms, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("scheduling/rooms/_table.html", {
        "rooms": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
    })


@login_required
@has_role('deptHead')
@transaction.atomic
def roomCreate(request):
    if request.method == 'POST':
        roomCode = request.POST.get('roomCode')
        building = request.POST.get('building')
        capacity = request.POST.get('capacity')
        type = request.POST.get('type')
        isActive = request.POST.get('isActive') == 'on'
        notes = request.POST.get('notes')

        Room.objects.create(
            roomCode=roomCode,
            building=building,
            capacity=capacity,
            type=type,
            isActive=isActive,
            notes=notes
        )

        messages.success(request, 'Room successfully added.')
        return redirect('roomList')

    return render(request, 'scheduling/rooms/create.html')


@login_required
@has_role('deptHead')
@transaction.atomic
def roomUpdate(request, roomId):
    room = get_object_or_404(Room, pk=roomId)

    if request.method == 'POST':
        room.roomCode = request.POST.get('roomCode')
        room.building = request.POST.get('building')
        room.capacity = request.POST.get('capacity')
        room.type = request.POST.get('type')
        room.isActive = request.POST.get('isActive') == 'on'
        room.notes = request.POST.get('notes')
        room.save()

        messages.success(request, 'Room updated successfully.')
        return redirect('roomList')

    return render(request, 'scheduling/rooms/update.html', {'room': room})


@login_required
@has_role('deptHead')
@transaction.atomic
def roomDelete(request, roomId):
    room = get_object_or_404(Room, pk=roomId)

    if request.method == 'POST':
        room.delete()
        messages.success(request, 'Room deleted.')
        return redirect('roomList')

    return render(request, 'scheduling/rooms/delete.html', {'room': room})



# ---------- GenEdSchedules ----------
@login_required
@has_role('deptHead')
def genedScheduleList(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    schedules = GenEdSchedule.objects.select_related("semester").order_by(
        "semester__name", "code", "sectionCode"
    )

    if query:
        schedules = schedules.filter(
            Q(semester__name__icontains=query) |
            Q(code__icontains=query) |
            Q(subjectName__icontains=query) |
            Q(sectionCode__icontains=query) |
            Q(instructorName__icontains=query) |
            Q(dayOfWeek__icontains=query)
        )

    paginator = Paginator(schedules, 10)
    page_obj = paginator.get_page(page)

    return render(request, "scheduling/genEdSchedules/list.html", {
        "schedules": page_obj,
        "query": query,
    })


@login_required
@has_role('deptHead')
def genedScheduleListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    schedules = GenEdSchedule.objects.select_related("semester").order_by(
        "semester__name", "code", "sectionCode"
    )

    if query:
        schedules = schedules.filter(
            Q(semester__name__icontains=query) |
            Q(code__icontains=query) |
            Q(subjectName__icontains=query) |
            Q(sectionCode__icontains=query) |
            Q(instructorName__icontains=query) |
            Q(dayOfWeek__icontains=query)
        )

    paginator = Paginator(schedules, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("scheduling/genEdSchedules/_table.html", {
        "schedules": page_obj,
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
    })


@login_required
@has_role('deptHead')
def genedScheduleCreate(request):
    semesters = Semester.objects.all().order_by('semesterId')  # assign the queryset

    if request.method == 'POST':
        semesterId = request.POST.get('semester')
        code = request.POST.get('code')
        subjectName = request.POST.get('subjectName')
        sectionCode = request.POST.get('sectionCode')
        instructorName = request.POST.get('instructorName') or None
        dayOfWeek = request.POST.get('dayOfWeek')
        startTime = request.POST.get('startTime')
        endTime = request.POST.get('endTime')

        semester = get_object_or_404(Semester, semesterId=semesterId) if semesterId else None  # use semesterId instead of id

        GenEdSchedule.objects.create(
            semester=semester,
            code=code,
            subjectName=subjectName,
            sectionCode=sectionCode,
            instructorName=instructorName,
            dayOfWeek=dayOfWeek,
            startTime=startTime,
            endTime=endTime,
        )
        messages.success(request, 'GenEd schedule created successfully.')
        return redirect('genedScheduleList')

    return render(request, 'scheduling/genEdSchedules/create.html', {'semesters': semesters})


@login_required
@has_role('deptHead')
def genedScheduleUpdate(request, scheduleId):
    schedule = get_object_or_404(GenEdSchedule, genedScheduleId=scheduleId)
    semesters = Semester.objects.all().order_by('semesterId')

    if request.method == 'POST':
        semesterId = request.POST.get('semester')
        schedule.semester = get_object_or_404(Semester, id=semesterId) if semesterId else None
        schedule.code = request.POST.get('code')
        schedule.subjectName = request.POST.get('subjectName')
        schedule.sectionCode = request.POST.get('sectionCode')
        schedule.instructorName = request.POST.get('instructorName') or None
        schedule.dayOfWeek = request.POST.get('dayOfWeek')
        schedule.startTime = request.POST.get('startTime')
        schedule.endTime = request.POST.get('endTime')

        schedule.save()
        messages.success(request, 'GenEd schedule updated successfully.')
        return redirect('genedScheduleList')

    return render(request, 'scheduling/genEdSchedules/update.html', {
        'schedule': schedule,
        'semesters': semesters
    })


@login_required
@has_role('deptHead')
def genedScheduleDelete(request, scheduleId):
    schedule = get_object_or_404(GenEdSchedule, genedScheduleId=scheduleId)

    if request.method == 'POST':
        schedule.delete()
        messages.success(request, 'GenEd schedule deleted.')
        return redirect('genedScheduleList')

    return render(request, 'scheduling/genEdSchedules/delete.html', {'schedule': schedule})


# ---------- Semesters ----------
@login_required
@has_role('deptHead')
def semesterList(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    semesters = Semester.objects.all().order_by("-createdAt")

    if query:
        semesters = semesters.filter(
            Q(name__icontains=query) |
            Q(term__icontains=query) |
            Q(academicYear__icontains=query)
        )

    paginator = Paginator(semesters, 10)
    page_obj = paginator.get_page(page)

    return render(request, "scheduling/semesters/list.html", {
        "semesters": page_obj,
        "query": query,
    })


@login_required
@has_role('deptHead')
def semesterListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    semesters = Semester.objects.all().order_by("-createdAt")

    if query:
        semesters = semesters.filter(
            Q(name__icontains=query) |
            Q(term__icontains=query) |
            Q(academicYear__icontains=query)
        )

    paginator = Paginator(semesters, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("scheduling/semesters/_table.html", {
        "semesters": page_obj,
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
def semesterCreate(request):
    if request.method == 'POST':
        academicYear = request.POST.get('academicYear')
        term = request.POST.get('term')
        isActive = bool(request.POST.get('isActive'))
        name = f"{term} Semester {academicYear}"

        if Semester.objects.filter(academicYear=academicYear, term=term).exists():
            messages.error(request, 'Semester for this academic year and term already exists.')
        else:
            Semester.objects.create(
                name=name,
                academicYear=academicYear,
                term=term,
                isActive=isActive
            )
            messages.success(request, 'Semester created successfully.')
            return redirect('semesterList')

    return render(request, 'scheduling/semesters/create.html')

@login_required
@has_role('deptHead')
def semesterUpdate(request, semesterId):
    semester = get_object_or_404(Semester, semesterId=semesterId)

    if request.method == 'POST':
        academicYear = request.POST.get('academicYear')
        term = request.POST.get('term')
        isActive = bool(request.POST.get('isActive'))
        name = f"{term} Semester {academicYear}"

        if Semester.objects.exclude(semesterId=semester.semesterId).filter(academicYear=academicYear, term=term).exists():
            messages.error(request, 'Another semester with this academic year and term already exists.')
        else:
            semester.name = name
            semester.academicYear = academicYear
            semester.term = term
            semester.isActive = isActive
            semester.save()
            messages.success(request, 'Semester updated successfully.')
            return redirect('semesterList')

    return render(request, 'scheduling/semesters/update.html', {'semester': semester})

from django.db.models import ProtectedError

@login_required
@has_role('deptHead')
def semesterDelete(request, semesterId):
    semester = get_object_or_404(Semester, semesterId=semesterId)

    if semester.isActive:
        messages.error(request, 'You cannot delete an active semester.')
        return redirect('semesterList')

    try:
        semester.delete()
        messages.success(request, 'Semester deleted successfully.')
    except ProtectedError:
        messages.error(request, 'Cannot delete this semester because it is linked to other records (e.g., schedules, enrollments).')

    return redirect('semesterList')




# ---------- Curriculum ----------
@login_required
@has_role('deptHead')
def curriculumList(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    curriculums = Curriculum.objects.all().order_by("-createdAt")

    if query:
        curriculums = curriculums.filter(
            Q(name__icontains=query) |
            Q(effectiveSy__icontains=query) |
            Q(description__icontains=query)
        )

    paginator = Paginator(curriculums, 10)
    page_obj = paginator.get_page(page)

    return render(request, "scheduling/curriculums/list.html", {
        "curriculums": page_obj,
        "query": query,
    })


@login_required
@has_role('deptHead')
def curriculumListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    curriculums = Curriculum.objects.all().order_by("-createdAt")

    if query:
        curriculums = curriculums.filter(
            Q(name__icontains=query) |
            Q(effectiveSy__icontains=query) |
            Q(description__icontains=query)
        )

    paginator = Paginator(curriculums, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("scheduling/curriculums/_table.html", {
        "curriculums": page_obj,
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
def curriculumCreate(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        effectiveSy = request.POST.get('effectiveSy')
        description = request.POST.get('description')

        if Curriculum.objects.filter(name=name).exists():
            messages.error(request, 'A curriculum with this name already exists.')
        else:
            Curriculum.objects.create(
                name=name,
                effectiveSy=effectiveSy,
                description=description
            )
            messages.success(request, 'Curriculum created successfully.')
            return redirect('curriculumList')

    return render(request, 'scheduling/curriculums/create.html')


@login_required
@has_role('deptHead')
def curriculumUpdate(request, curriculumId):
    curriculum = get_object_or_404(Curriculum, curriculumId=curriculumId)

    if request.method == 'POST':
        name = request.POST.get('name')
        effectiveSy = request.POST.get('effectiveSy')
        description = request.POST.get('description')

        if Curriculum.objects.exclude(curriculumId=curriculum.curriculumId).filter(name=name).exists():
            messages.error(request, 'Another curriculum with this name already exists.')
        else:
            curriculum.name = name
            curriculum.effectiveSy = effectiveSy
            curriculum.description = description
            curriculum.save()
            messages.success(request, 'Curriculum updated successfully.')
            return redirect('curriculumList')

    return render(request, 'scheduling/curriculums/update.html', {'curriculum': curriculum})


@login_required
@has_role('deptHead')
def curriculumDelete(request, curriculumId):
    curriculum = get_object_or_404(Curriculum, curriculumId=curriculumId)

    try:
        curriculum.delete()
        messages.success(request, 'Curriculum deleted successfully.')
    except ProtectedError:
        messages.error(request, 'Cannot delete this curriculum because it has linked subjects.')

    return redirect('curriculumList')


@login_required
@has_role('deptHead')
def curriculumDetail(request, curriculumId):
    curriculum = get_object_or_404(Curriculum, curriculumId=curriculumId)
    subjects = curriculum.subjects.all().order_by('yearLevel', 'defaultTerm')
    return render(request, 'scheduling/curriculums/detail.html', {
        'curriculum': curriculum,
        'subjects': subjects
    })


# ---------- Semesters ----------
@login_required
@has_role('deptHead')
def semesterList(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    semesters = Semester.objects.all().order_by("-createdAt")

    if query:
        semesters = semesters.filter(
            Q(name__icontains=query) |
            Q(term__icontains=query) |
            Q(academicYear__icontains=query)
        )

    paginator = Paginator(semesters, 10)
    page_obj = paginator.get_page(page)

    return render(request, "scheduling/semesters/list.html", {
        "semesters": page_obj,
        "query": query,
    })


@login_required
@has_role('deptHead')
def semesterListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    semesters = Semester.objects.all().order_by("-createdAt")

    if query:
        semesters = semesters.filter(
            Q(name__icontains=query) |
            Q(term__icontains=query) |
            Q(academicYear__icontains=query)
        )

    paginator = Paginator(semesters, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("scheduling/semesters/_table.html", {
        "semesters": page_obj,
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
def semesterCreate(request):
    if request.method == 'POST':
        academicYear = request.POST.get('academicYear')
        term = request.POST.get('term')
        isActive = bool(request.POST.get('isActive'))
        name = f"{term} Semester {academicYear}"

        if Semester.objects.filter(academicYear=academicYear, term=term).exists():
            messages.error(request, 'Semester for this academic year and term already exists.')
        else:
            Semester.objects.create(
                name=name,
                academicYear=academicYear,
                term=term,
                isActive=isActive
            )
            messages.success(request, 'Semester created successfully.')
            return redirect('semesterList')

    return render(request, 'scheduling/semesters/create.html')

@login_required
@has_role('deptHead')
def semesterUpdate(request, semesterId):
    semester = get_object_or_404(Semester, semesterId=semesterId)

    if request.method == 'POST':
        academicYear = request.POST.get('academicYear')
        term = request.POST.get('term')
        isActive = bool(request.POST.get('isActive'))
        name = f"{term} Semester {academicYear}"

        if Semester.objects.exclude(semesterId=semester.semesterId).filter(academicYear=academicYear, term=term).exists():
            messages.error(request, 'Another semester with this academic year and term already exists.')
        else:
            semester.name = name
            semester.academicYear = academicYear
            semester.term = term
            semester.isActive = isActive
            semester.save()
            messages.success(request, 'Semester updated successfully.')
            return redirect('semesterList')

    return render(request, 'scheduling/semesters/update.html', {'semester': semester})

from django.db.models import ProtectedError

@login_required
@has_role('deptHead')
def semesterDelete(request, semesterId):
    semester = get_object_or_404(Semester, semesterId=semesterId)

    if semester.isActive:
        messages.error(request, 'You cannot delete an active semester.')
        return redirect('semesterList')

    try:
        semester.delete()
        messages.success(request, 'Semester deleted successfully.')
    except ProtectedError:
        messages.error(request, 'Cannot delete this semester because it is linked to other records (e.g., schedules, enrollments).')

    return redirect('semesterList')



# ---------- Subject Offerings ----------
@login_required
@has_role('deptHead')
def subjectOfferingList(request):
    # Dropdown data (only active)
    curricula = Curriculum.objects.filter(isActive=True).order_by("-createdAt")
    semesters = Semester.objects.filter(isActive=True).order_by("-createdAt")

    # Get selected curriculum & semester
    selected_curriculum_id = request.GET.get("curriculum")
    selected_semester_id = request.GET.get("semester")

    selected_curriculum = (
        get_object_or_404(Curriculum, pk=selected_curriculum_id, isActive=True)
        if selected_curriculum_id else curricula.first()
    )
    selected_semester = (
        get_object_or_404(Semester, pk=selected_semester_id, isActive=True)
        if selected_semester_id else semesters.first()
    )

    # Get offerings for this semester & curriculum
    offerings = SubjectOffering.objects.filter(
        semester=selected_semester,
        subject__curriculum=selected_curriculum
    ).select_related("subject", "semester")

    # 🔹 Fallback: Auto-create offerings if none exist yet
    if not offerings.exists():
        subjects_for_sem = Subject.objects.filter(
            curriculum=selected_curriculum,
            defaultTerm__in=[
                0 if selected_semester.term == "1st" else
                1 if selected_semester.term == "2nd" else
                2
            ]
        )
        for subj in subjects_for_sem:
            SubjectOffering.objects.get_or_create(
                subject=subj,
                semester=selected_semester,
                defaults={"numberOfSections": 6}
            )
        offerings = SubjectOffering.objects.filter(
            semester=selected_semester,
            subject__curriculum=selected_curriculum
        ).select_related("subject", "semester")

    # Group offerings by year level
    grouped_offerings = []
    for year in [1, 2, 3, 4]:
        year_offerings = [o for o in offerings if o.subject.yearLevel == year]
        grouped_offerings.append((year, year_offerings))

    return render(request, "scheduling/offerings/list.html", {
        "curricula": curricula,
        "semesters": semesters,
        "selected_curriculum": selected_curriculum,
        "selected_semester": selected_semester,
        "grouped_offerings": grouped_offerings,
    })
3


@login_required
@has_role('deptHead')
def subjectOfferingListLive(request):
    query = request.GET.get("q", "").strip()
    page = int(request.GET.get("page", 1))

    offerings = SubjectOffering.objects.select_related("subject", "semester").order_by(
        "subject__yearLevel", "subject__code"
    )

    if query:
        offerings = offerings.filter(
            Q(subject__code__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(semester__name__icontains=query) |
            Q(semester__academicYear__icontains=query)
        )

    grouped_offerings = []
    for year in range(1, 5):
        year_offerings = [o for o in offerings if o.subject.yearLevel == year]
        grouped_offerings.append((year, year_offerings))

    paginator = Paginator(offerings, 10)
    page_obj = paginator.get_page(page)

    html = render_to_string("scheduling/offerings/_table.html", {
        "grouped_offerings": grouped_offerings
    }, request=request)

    return JsonResponse({
        "html": html,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
    })



@login_required
@has_role('deptHead')
def subjectOfferingUpdate(request, offeringId):
    offering = get_object_or_404(SubjectOffering, pk=offeringId)

    if request.method == "POST":
        try:
            numberOfSections = int(request.POST.get("numberOfSections", offering.numberOfSections))
            offering.numberOfSections = numberOfSections
            offering.save()
            messages.success(request, f"Updated {offering.subject.code} to {numberOfSections} sections.")
            return redirect("subjectOfferingList")
        except ValueError:
            messages.error(request, "Invalid number of sections entered.")

    return render(request, "scheduling/offerings/update.html", {
        "offering": offering,
    })


@login_required
@has_role('deptHead')
def generateSections(request, semesterId, curriculumId):
    semester = get_object_or_404(Semester, pk=semesterId)
    curriculum = get_object_or_404(Curriculum, pk=curriculumId)

    offerings = SubjectOffering.objects.filter(
        semester=semester,
        subject__curriculum=curriculum,
        status="active"
    )

    added, removed = 0, 0
    letters = list(string.ascii_uppercase)

    for offering in offerings:
        existing_sections = list(
            Section.objects.filter(subject=offering.subject, semester=semester).order_by("sectionId")
        )
        required_sections = offering.numberOfSections

        if len(existing_sections) < required_sections:
            for i in range(len(existing_sections), required_sections):
                section_code = f"{offering.subject.code}-{letters[i]}"
                Section.objects.create(
                    subject=offering.subject,
                    semester=semester,
                    sectionCode=section_code,
                    status="active",
                )
                added += 1

        elif len(existing_sections) > required_sections:
            to_remove = existing_sections[required_sections:]
            for section in to_remove:
                section.delete()
                removed += 1

    if added or removed:
        messages.success(
            request,
            f"Sections updated: {added} added, {removed} removed for {semester.name} ({curriculum.name})."
        )
    else:
        messages.info(
            request,
            f"All sections already match the set numbers for {semester.name} ({curriculum.name})."
        )

    return redirect("subjectOfferingList")
