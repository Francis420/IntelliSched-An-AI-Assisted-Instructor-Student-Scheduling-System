# scheduling/views.py
from django.shortcuts import render
from scheduling.models import Schedule, Semester, Section, Room
from core.models import Instructor, UserLogin
from django.contrib.auth.decorators import login_required
from collections import defaultdict
from django.http import JsonResponse
from scheduler.tasks import run_scheduler_task
from scheduler.models import SchedulerProgress
from celery import current_app
import uuid
import os, signal


def scheduleOutput(request):
    # 1. Retrieve filter parameters
    semester_id = request.GET.get("semester")
    instructor_id = request.GET.get("instructor")
    section_id = request.GET.get("section")
    room_id = request.GET.get("room")  # <--- NEW
    day = request.GET.get("day")
    start_time = request.GET.get("start_time")
    schedule_type = request.GET.get("schedule_type")

    # 2. Base queryset
    schedules = Schedule.objects.select_related(
        "subject", "instructor", "section", "room", "semester"
    ).filter(status="active")

    # 3. Apply filters
    if semester_id:
        schedules = schedules.filter(semester__semesterId=semester_id)
    if instructor_id:
        schedules = schedules.filter(instructor__instructorId=instructor_id)
    if section_id:
        schedules = schedules.filter(section__sectionId=section_id)
    if room_id:
        schedules = schedules.filter(room__roomId=room_id) # <--- NEW
    if day:
        schedules = schedules.filter(dayOfWeek=day)
    if start_time:
        schedules = schedules.filter(startTime=start_time)
    if schedule_type:
        schedules = schedules.filter(scheduleType=schedule_type)

    # 4. Order neatly
    # Current Sort Order: Subject -> Section -> Instructor Name -> Room
    schedules = schedules.order_by(
        "subject__code",
        "section__sectionCode",
        "instructor__userlogin__user__lastName", 
        "instructor__userlogin__user__firstName",
        "room__roomCode" 
    ).distinct()

    # 5. Dropdown data
    semesters = Semester.objects.all().order_by("-createdAt")
    
    # Instructors sorted by name
    instructors = Instructor.objects.all().order_by(
        "userlogin__user__lastName", 
        "userlogin__user__firstName"
    ).distinct()
    
    sections = Section.objects.filter(status="active").order_by("sectionCode")
    
    # Rooms sorted by code (NEW)
    rooms = Room.objects.filter(isActive=True).order_by("roomCode")

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # distinct values for dropdowns
    times = Schedule.objects.values_list('startTime', flat=True).distinct().order_by('startTime')
    types = Schedule.objects.values_list('scheduleType', flat=True).distinct().order_by('scheduleType')

    context = {
        "schedules": schedules,
        "semesters": semesters,
        "instructors": instructors,
        "sections": sections,
        "rooms": rooms,     # <--- Pass rooms to template
        "days": days,
        "times": times,
        "types": types,
        # Maintain selection state
        "selected_semester": semester_id,
        "selected_instructor": instructor_id,
        "selected_section": section_id,
        "selected_room": room_id, # <--- Maintain state
        "selected_day": day,
        "selected_time": start_time,
        "selected_type": schedule_type,
    }
    return render(request, "scheduler/scheduleOutput.html", context)


# Individual Instructor Schedule View
@login_required
def instructorScheduleView(request):
    user = request.user
    login_entry = UserLogin.objects.filter(user=user).select_related("instructor").first()

    if not login_entry or not login_entry.instructor:
        return render(request, "scheduling/instructor_schedule.html", {
            "error": "No instructor profile found for this account."
        })

    instructor = login_entry.instructor

    schedules = (
        Schedule.objects.select_related("subject", "section", "room", "semester")
        .filter(instructor=instructor, status="active")
        .order_by("dayOfWeek", "startTime")
    )

    from collections import defaultdict
    grouped = defaultdict(list)
    for sched in schedules:
        grouped[sched.dayOfWeek].append(sched)

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    grouped_schedules = [(day, grouped[day]) for day in day_order if grouped[day]]

    context = {
        "instructor": instructor,
        "grouped_schedules": grouped_schedules,
    }
    return render(request, "scheduler/instructorSchedule.html", context)


# Scdeduler Dashboard View
def scheduler_dashboard(request):
    batch_id = str(uuid.uuid4())
    return render(request, "scheduler/schedulerDashboard.html", {"batch_id": batch_id})

def start_scheduler(request):
    batch_id = request.GET.get("batch_id")
    progress, _ = SchedulerProgress.objects.get_or_create(batch_id=batch_id)
    task = run_scheduler_task.delay(batch_id=batch_id)
    progress.task_id = task.id
    progress.status = "running"
    progress.save()
    return JsonResponse({"message": "Scheduling started.", "batch_id": batch_id, "task_id": task.id})

def stop_scheduler(request):
    batch_id = request.GET.get("batch_id")
    try:
        progress = SchedulerProgress.objects.get(batch_id=batch_id)

        # Kill subprocess if still running
        if progress.process_pid:
            try:
                os.kill(progress.process_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # Process already exited

        # Also revoke Celery task to stop any background logic
        if progress.task_id:
            current_app.control.revoke(progress.task_id, terminate=True, signal="SIGTERM")

        progress.status = "stopped"
        progress.message = "Scheduler manually stopped."
        progress.save()

        return JsonResponse({"status": "stopped", "message": "Scheduler has been stopped."})
    except SchedulerProgress.DoesNotExist:
        return JsonResponse({"status": "error", "message": "No running scheduler found."})
    

def scheduler_status(request):
    batch_id = request.GET.get("batch_id")
    if not batch_id:
        return JsonResponse({"error": "Missing batch_id"}, status=400)

    try:
        progress = SchedulerProgress.objects.get(batch_id=batch_id)
    except SchedulerProgress.DoesNotExist:
        return JsonResponse({"status": "idle", "message": "No progress found."})

    return JsonResponse({
        "status": progress.status,
        "message": progress.message,
        "progress": progress.progress,
        "logs": progress.logs[-20:],
    })