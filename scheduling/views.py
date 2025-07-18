from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from authapi.views import has_role  
from scheduling.models import Room, GenEdSchedule, Semester
from django.db import transaction


# ---------- Rooms ----------
@login_required
@has_role('deptHead')
def roomList(request):
    rooms = Room.objects.all().order_by('roomCode')
    return render(request, 'scheduling/rooms/list.html', {'rooms': rooms})


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
    schedules = GenEdSchedule.objects.select_related('semester').order_by('semester__name', 'code', 'sectionCode')
    return render(request, 'scheduling/genEdSchedules/list.html', {'schedules': schedules})


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
    semesters = Semester.objects.all().order_by('-id')

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