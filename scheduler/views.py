# scheduling/views.py
from django.shortcuts import render
from scheduling.models import Schedule, Semester
from core.models import Instructor, UserLogin
from django.contrib.auth.decorators import login_required
from collections import defaultdict
from django.http import JsonResponse
from scheduler.tasks import run_scheduler_task
from scheduler.models import SchedulerProgress
from celery import current_app
import uuid
import os, signal

# Scheduler Output View
def scheduleOutput(request):
    # Retrieve filter parameters
    semester_id = request.GET.get("semester")
    instructor_id = request.GET.get("instructor")
    day = request.GET.get("day")

    # Base queryset
    schedules = Schedule.objects.select_related(
        "subject", "instructor", "section", "room", "semester"
    ).filter(status="active")

    # Apply filters
    if semester_id:
        schedules = schedules.filter(semester__semesterId=semester_id)
    if instructor_id:
        schedules = schedules.filter(instructor__instructorId=instructor_id)
    if day:
        schedules = schedules.filter(dayOfWeek=day)

    # Order neatly
    schedules = schedules.order_by("dayOfWeek", "startTime")

    # Dropdown data
    semesters = Semester.objects.all().order_by("-createdAt")
    instructors = Instructor.objects.all().order_by("instructorId")
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    context = {
        "schedules": schedules,
        "semesters": semesters,
        "instructors": instructors,
        "days": days,
        "selected_semester": semester_id,
        "selected_instructor": instructor_id,
        "selected_day": day,
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