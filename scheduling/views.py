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
    InstructorSchedulingConfiguration,
)
from core.models import (
    UserLogin,
    Instructor,
)
from django.db import transaction
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import Q
import string
from django.urls import reverse
from scheduling.services import getPreSchedulingAnalysis



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
        name = f"{term} Semester {academicYear}"

        if Semester.objects.filter(academicYear=academicYear, term=term).exists():
            messages.error(request, 'Semester for this academic year and term already exists.')
        else:
            Semester.objects.update(isActive=False)

            Semester.objects.create(
                name=name,
                academicYear=academicYear,
                term=term,
                isActive=True
            )

            messages.success(request, f'{name} created and set as active.')
            return redirect('semesterList')

    return render(request, 'scheduling/semesters/create.html')

@login_required
@has_role('deptHead')
def semesterUpdate(request, semesterId):
    semester = get_object_or_404(Semester, semesterId=semesterId)

    if request.method == 'POST':
        academicYear = request.POST.get('academicYear')
        term = request.POST.get('term')
        isActive = request.POST.get('isActive') == 'on'  # ✅ checkbox logic
        name = f"{term} Semester {academicYear}"

        # Prevent duplicate (same term + year)
        if Semester.objects.exclude(semesterId=semester.semesterId).filter(
            academicYear=academicYear, term=term
        ).exists():
            messages.error(request, 'Another semester with this academic year and term already exists.')
        else:
            # ✅ If this semester is being activated, deactivate others
            if isActive:
                Semester.objects.exclude(semesterId=semester.semesterId).update(isActive=False)

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
        
        # --- NEW SIGNATURE FIELDS ---
        dean = request.POST.get('dean')
        vicePresidentForAcademicAffairs = request.POST.get('vicePresidentForAcademicAffairs')
        universityPresident = request.POST.get('universityPresident')
        # ----------------------------

        if Curriculum.objects.filter(name=name).exists():
            messages.error(request, 'A curriculum with this name already exists.')
        else:
            Curriculum.objects.create(
                name=name,
                effectiveSy=effectiveSy,
                description=description,
                dean=dean,
                vicePresidentForAcademicAffairs=vicePresidentForAcademicAffairs,
                universityPresident=universityPresident
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
        dean = request.POST.get('dean')
        vicePresidentForAcademicAffairs = request.POST.get('vicePresidentForAcademicAffairs')
        universityPresident = request.POST.get('universityPresident')

        if Curriculum.objects.exclude(curriculumId=curriculum.curriculumId).filter(name=name).exists():
            messages.error(request, 'Another curriculum with this name already exists.')
        else:
            curriculum.name = name
            curriculum.effectiveSy = effectiveSy
            curriculum.description = description
            curriculum.dean = dean
            curriculum.vicePresidentForAcademicAffairs = vicePresidentForAcademicAffairs
            curriculum.universityPresident = universityPresident
            
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

    # Optimize query with select_related since we will show curriculum name
    semesters = Semester.objects.select_related('curriculum').all().order_by("-createdAt")

    if query:
        semesters = semesters.filter(
            Q(name__icontains=query) |
            Q(term__icontains=query) |
            Q(academicYear__icontains=query) |
            Q(curriculum__name__icontains=query) # Added search by curriculum
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

    semesters = Semester.objects.select_related('curriculum').all().order_by("-createdAt")

    if query:
        semesters = semesters.filter(
            Q(name__icontains=query) |
            Q(term__icontains=query) |
            Q(academicYear__icontains=query) |
            Q(curriculum__name__icontains=query)
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
    # Fetch active curriculums for the dropdown
    curriculums = Curriculum.objects.filter(isActive=True).order_by('-createdAt')

    if request.method == 'POST':
        curriculum_id = request.POST.get('curriculum')
        academicYear = request.POST.get('academicYear')
        term = request.POST.get('term')
        isActive = request.POST.get('isActive') == 'on'
        
        # Get Curriculum Instance
        curriculum = get_object_or_404(Curriculum, pk=curriculum_id)

        # Name format: "1st Semester 2025-2026 (Curriculum Name)"
        name = f"{term} Semester {academicYear}"

        # Validation: Check if this specific combo exists
        if Semester.objects.filter(academicYear=academicYear, term=term, curriculum=curriculum).exists():
            messages.error(request, 'A semester for this curriculum, academic year, and term already exists.')
        else:
            Semester.objects.create(
                name=name,
                curriculum=curriculum,
                academicYear=academicYear,
                term=term,
                isActive=isActive
            )
            messages.success(request, 'Semester created successfully.')
            return redirect('semesterList')

    return render(request, 'scheduling/semesters/create.html', {
        'curriculums': curriculums
    })


@login_required
@has_role('deptHead')
def semesterUpdate(request, semesterId):
    semester = get_object_or_404(Semester, semesterId=semesterId)
    curriculums = Curriculum.objects.filter(isActive=True).order_by('-createdAt')

    if request.method == 'POST':
        curriculum_id = request.POST.get('curriculum')
        academicYear = request.POST.get('academicYear')
        term = request.POST.get('term')
        isActive = request.POST.get('isActive') == 'on'
        
        curriculum = get_object_or_404(Curriculum, pk=curriculum_id)
        name = f"{term} Semester {academicYear}"

        # Validation: Exclude current self, check if combo exists
        if Semester.objects.exclude(semesterId=semester.semesterId).filter(
            academicYear=academicYear, term=term, curriculum=curriculum
        ).exists():
            messages.error(request, 'Another semester with this curriculum, academic year, and term already exists.')
        else:
            semester.name = name
            semester.curriculum = curriculum
            semester.academicYear = academicYear
            semester.term = term
            semester.isActive = isActive
            semester.save()
            messages.success(request, 'Semester updated successfully.')
            return redirect('semesterList')

    return render(request, 'scheduling/semesters/update.html', {
        'semester': semester,
        'curriculums': curriculums
    })


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
        messages.error(request, 'Cannot delete this semester because it is linked to other records (e.g., schedules).')

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
                # UPDATED: Set a default for numberOfSections and the new student count
                defaults={"numberOfSections": 6, "defaultStudentsPerSection": 40} 
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
@transaction.atomic
def generateSections(request, semesterId, curriculumId):
    semester = get_object_or_404(Semester, pk=semesterId)
    curriculum = get_object_or_404(Curriculum, pk=curriculumId)

    offerings = SubjectOffering.objects.filter(
        semester=semester,
        subject__curriculum=curriculum,
        status="active"
    ).select_related('subject')
    
    # Default capacity for newly created sections
    DEFAULT_STUDENT_COUNT = 40

    added, removed, updated_units = 0, 0, 0 # Renamed 'updated_students' to 'updated_units' as we only force save()
    letters = list(string.ascii_uppercase)

    for offering in offerings:
        required_sections = offering.numberOfSections
        existing_sections = list(
            Section.objects.filter(subject=offering.subject, semester=semester).order_by("sectionId")
        )

        # 1. Create missing sections
        if len(existing_sections) < required_sections:
            for i in range(len(existing_sections), required_sections):
                section_code = f"{offering.subject.code}-{letters[i]}"
                Section.objects.create(
                    subject=offering.subject,
                    semester=semester,
                    sectionCode=section_code,
                    numberOfStudents=DEFAULT_STUDENT_COUNT, # <-- NEW: Set default student count
                    status="active",
                )
                added += 1

        # 2. Remove excess sections
        elif len(existing_sections) > required_sections:
            to_remove = existing_sections[required_sections:]
            for section in to_remove:
                section.delete()
                removed += 1
        
        # 3. Update existing sections (to ensure units/minutes are synced from Subject model)
        for section in existing_sections[:required_sections]:
            # If a section was created with default=0 (before this change), update it to a standard default
            if section.numberOfStudents == 0:
                 section.numberOfStudents = DEFAULT_STUDENT_COUNT
                 section.save()
                 updated_units += 1 # Use this counter for general updates
            else:
                 # Call save() to ensure units/minutes/lab status are updated from the Subject's save() hook
                 section.save()
                 updated_units += 1


    if added or removed or updated_units:
        messages.success(
            request,
            f"Sections successfully updated for {semester.name} ({curriculum.name}): {added} added, {removed} removed."
        )
    else:
        messages.info(
            request,
            f"All sections already match the required count for {semester.name} ({curriculum.name})."
        )

    return redirect("subjectOfferingList")

# Add this new function to your views.py
from django.db import transaction

@login_required
@has_role('deptHead')
def sectionConfigList(request, offeringId):
    offering = get_object_or_404(SubjectOffering, pk=offeringId)
    
    sections = Section.objects.filter(
        subject=offering.subject, 
        semester=offering.semester,
        status='active'
    ).order_by('sectionCode')

    if request.method == 'POST':
        with transaction.atomic():
            # Iterate through POST data and update sections
            for section in sections:
                # The input field names in the template will be 'students_SECTION_ID'
                field_name = f'students_{section.sectionId}'
                
                try:
                    new_capacity = request.POST.get(field_name)
                    if new_capacity is not None:
                        new_capacity = int(new_capacity)
                        if new_capacity < 1:
                            raise ValueError("Capacity must be a positive number.")

                        if section.numberOfStudents != new_capacity:
                            section.numberOfStudents = new_capacity
                            section.save()
                            
                except ValueError as e:
                    messages.error(request, f"Invalid capacity entered for section {section.sectionCode}.")
                    # Render the page again to show the error
                    return render(request, "scheduling/sections/config_list.html", {
                        "offering": offering,
                        "sections": sections,
                    })
        
            messages.success(request, f"Section capacities for {offering.subject.code} updated successfully.")
            return redirect('subjectOfferingList')

    # GET request
    return render(request, "scheduling/sections/config_list.html", {
        "offering": offering,
        "sections": sections,
    })


@login_required
@has_role('deptHead')
def instructorSchedulingConfig(request):
    # Fetch the active config or create a default one if it doesn't exist
    config = InstructorSchedulingConfiguration.objects.filter(is_active=True).first()
    if not config:
        config = InstructorSchedulingConfiguration.objects.create(is_active=True)

    if request.method == "POST":
        try:
            config.overload_limit_with_designation = float(request.POST.get('overload_limit_with_designation', 9.0))
            config.overload_limit_no_designation = float(request.POST.get('overload_limit_no_designation', 12.0))
            config.part_time_normal_limit = float(request.POST.get('part_time_normal_limit', 15.0))
            config.part_time_overload_limit = float(request.POST.get('part_time_overload_limit', 0.0))
            config.pure_overload_normal_limit = float(request.POST.get('pure_overload_normal_limit', 0.0))
            config.pure_overload_max_limit = float(request.POST.get('pure_overload_max_limit', 12.0))
            config.save()
            
            messages.success(request, "Instructor scheduling configuration updated successfully.")
            return redirect('instructorSchedulingConfig')
        except ValueError:
            messages.error(request, "Invalid input. Please enter valid numbers for hours.")

    return render(request, 'scheduling/instructorConfig.html', {
        'config': config,
    })


@login_required
@has_role('deptHead')
def preSchedulingDetailedAnalysis(request):
    """
    Detailed view for Supply vs Demand analysis with Semester Selector.
    """
    # 1. Handle Semester Selection
    semester_id = request.GET.get('semester')
    
    if semester_id:
        selected_semester = get_object_or_404(Semester, pk=semester_id)
    else:
        # Default to active, or last created if no active exists
        selected_semester = Semester.objects.filter(isActive=True).first()
        if not selected_semester:
            selected_semester = Semester.objects.last()

    # 2. Get list of all semesters for the dropdown
    all_semesters = Semester.objects.all().order_by('-academicYear', '-term')

    # 3. Calculate Analysis
    analysis_data = None
    if selected_semester:
        analysis_data = getPreSchedulingAnalysis(selected_semester)

    context = {
        'semesters': all_semesters,
        'selected_semester': selected_semester,
        'analysis': analysis_data
    }
    
    return render(request, 'scheduling/preSchedulingDetailedAnalysis.html', context)