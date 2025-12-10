# scheduler/views.py
from django.shortcuts import render, redirect
from django.urls import reverse
from django.db import transaction
from scheduling.models import Schedule, Semester, Section, Room
from core.models import Instructor, UserLogin, User
from django.contrib.auth.decorators import login_required
from collections import defaultdict
from django.http import JsonResponse
from scheduler.tasks import run_scheduler_task
from scheduler.models import SchedulerProgress
from celery import current_app
import uuid
import os, signal
from django.contrib import messages
from datetime import datetime, timedelta
from django.utils import timezone
from authapi.views import has_role  


@login_required
@has_role('deptHead')
def finalizeSchedule(request, semester_id): 
    if request.method == 'POST':
        # semester_id is now retrieved from the URL path as a positional argument
        
        # Check if the currently active schedule is the one being finalized
        active_schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='active')
        
        if active_schedules.exists():
            try:
                with transaction.atomic():
                    # Archive any previously finalized schedules for the same semester
                    Schedule.objects.filter(semester__semesterId=semester_id, status='finalized').update(status='archived')
                    
                    # Set the current active schedules to finalized
                    active_schedules.update(status='finalized')
                    
                    messages.success(request, "Schedule successfully FINALIZED and locked.")
            except Exception as e:
                messages.error(request, f"Failed to finalize schedule: {e}")
        else:
            messages.warning(request, "No active schedule found to finalize.")
            
        return redirect(reverse('schedule_output') + f'?semester={semester_id}&batch_key=finalized')
    return redirect('schedule_output')

# --- NEW REVERT VIEW ---
@login_required
@has_role('deptHead')
def revertSchedule(request):
    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('schedule_output')

    semester_id = request.POST.get('semester_id')
    batch_key = request.POST.get('batch_key')

    # Guard clause: Ensure a valid archived batch key is provided
    if not semester_id or not batch_key or batch_key in ['active', 'finalized', 'none']:
        messages.error(request, "Invalid selection for reversion. Please select an archived run.")
        return redirect('schedule_output')

    try:
        # 1. Parse and validate the selected batch time (using Python truncation logic)
        selected_timestamp = datetime.fromisoformat(batch_key)
        
        # Ensure timezone awareness and normalize
        if selected_timestamp.tzinfo is None:
            selected_timestamp = timezone.make_aware(selected_timestamp)
        else:
            selected_timestamp = selected_timestamp.astimezone(timezone.get_current_timezone())
        
        # Truncate microseconds to match the batching logic in scheduleOutput
        selected_timestamp = selected_timestamp.replace(microsecond=0)

        # 2. Perform the Atomic Swap
        with transaction.atomic():
            
            # A. Archive the CURRENT active schedules (preserving them)
            Schedule.objects.filter(
                semester__semesterId=semester_id, 
                status='active'
            ).update(status='archived') 
            
            # B. Revert the SELECTED ARCHIVED schedules back to 'active'
            # Filter using the 1-second range around the truncated timestamp
            num_reverted = Schedule.objects.filter(
                semester__semesterId=semester_id, 
                status='archived',
                createdAt__gte=selected_timestamp,
                createdAt__lt=selected_timestamp + timedelta(seconds=1),
            ).update(status='active')

        if num_reverted > 0:
            messages.success(request, f"Successfully reverted {num_reverted} schedules to the active draft from the run: {selected_timestamp.strftime('%b %d, %I:%M %p')}.")
        else:
            messages.warning(request, "No schedules were found for the selected archived run. Nothing was reverted.")

    except (ValueError, Exception) as e:
        messages.error(request, f"An error occurred during schedule reversion: {e}")
        
    # Redirect to view the newly active schedule
    return redirect(reverse('schedule_output') + f'?semester={semester_id}&batch_key=active')


# --- UPDATED scheduleOutput View (FIXED Instructor Aggregation) ---
@login_required
@has_role('deptHead')
def scheduleOutput(request):
    # 1. Retrieve or Default Semester ID
    semester_id = request.GET.get("semester")
    if not semester_id:
        latest_semester = Semester.objects.order_by("-createdAt").first()
        if latest_semester:
            semester_id = str(latest_semester.semesterId)
        else:
            return render(request, "scheduler/scheduleOutput.html", {"error": "No semesters found."})

    # --- BATCH SELECTION LOGIC ---
    
    batch_key = request.GET.get("batch_key", 'active') 
    
    # 1. Get all unique creation timestamps and group them in Python
    raw_archived_datetimes = Schedule.objects.filter(
        semester__semesterId=semester_id, 
        status='archived'
    ).order_by('-createdAt').values_list('createdAt', flat=True).distinct()

    # Use a dictionary to collect only one datetime per unique 'second' timestamp
    unique_batch_times = {}
    for dt in raw_archived_datetimes:
        # Truncate the datetime to the second in Python to simulate TruncSecond
        truncated_dt_key = dt.replace(microsecond=0)
        if truncated_dt_key not in unique_batch_times:
            unique_batch_times[truncated_dt_key] = truncated_dt_key

    # Get the sorted list of unique batch datetimes
    archived_batch_times = sorted(unique_batch_times.keys(), reverse=True)
    
    # Build a list of choices for the template dropdown
    batch_choices = [
        {'key': 'active', 'name': 'Current Active Draft'},
        {'key': 'finalized', 'name': 'FINALIZED Schedule (Locked)'},
    ] + [
        {'key': batch_time.isoformat(), 'name': f"Archived Run: {batch_time.strftime('%b %d, %Y %I:%M %p')}"} 
        for batch_time in archived_batch_times
    ]
    
    # 2. Determine which schedules to display
    
    if batch_key == 'finalized':
        schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='finalized')
        current_display_status = 'Finalized Schedule'
    
    elif batch_key == 'active':
        schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='active')
        current_display_status = 'Active Draft'
        
    else:
        # User selected an archived batch
        try:
            selected_timestamp = datetime.fromisoformat(batch_key)
            
            if selected_timestamp.tzinfo is None:
                selected_timestamp = timezone.make_aware(selected_timestamp)
            else:
                selected_timestamp = selected_timestamp.astimezone(timezone.get_current_timezone())
            
            selected_timestamp = selected_timestamp.replace(microsecond=0)
            
            # Filter the database records using the 1-second range
            schedules = Schedule.objects.filter(
                semester__semesterId=semester_id, 
                createdAt__gte=selected_timestamp,
                createdAt__lt=selected_timestamp + timedelta(seconds=1),
                status='archived'
            )
            current_display_status = f"Archived Run ({selected_timestamp.strftime('%b %d, %I:%M %p')})"
            
        except ValueError:
            # Fallback if the timestamp key is invalid
            schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='active')
            current_display_status = 'Active Draft'
            batch_key = 'active'
            
    # --- Fallback Check: If the requested batch is empty, fall back to the newest archived run ---
    if not schedules.exists() and batch_key in ['active', 'finalized']:
        if archived_batch_times: 
            latest_batch_time = archived_batch_times[0]
            
            schedules = Schedule.objects.filter(
                semester__semesterId=semester_id, 
                createdAt__gte=latest_batch_time,
                createdAt__lt=latest_batch_time + timedelta(seconds=1),
                status='archived'
            )
            current_display_status = f"Archived Run ({latest_batch_time.strftime('%b %d, %I:%M %p')})"
            batch_key = latest_batch_time.isoformat()
        else:
            schedules = Schedule.objects.none()
            current_display_status = 'No Schedules Found'
            batch_key = 'none'


    # 3. Fetch Data with necessary lookups
    schedules = schedules.select_related(
        'instructor', 
        'room'
    ).prefetch_related(
        # This prefetch is necessary for schedule.instructor.full_name property
        'instructor__userlogin_set__user'
    ).order_by('dayOfWeek', 'startTime')
    
    # --- Aggregation Dictionaries Initialization and Logic (FIXED: Uses unique ID) ---
    room_usage = defaultdict(lambda: {"total_minutes": 0, "usage_hours": 0.0})
    instructor_load = defaultdict(lambda: {
        "id": None, "name": None, "normal_min": 0, "overload_min": 0, "total_hours": 0.0,
        "daily_spread": defaultdict(int)
    })
    
    for schedule in schedules:
        # Use Schedule model's property for duration
        duration_minutes = schedule.duration_minutes
        
        # Room Usage (This works)
        room_name = schedule.room.roomCode if schedule.room else "TBA"
        room_usage[room_name]["total_minutes"] += duration_minutes

        # Instructor Load and Daily Spread 
        if schedule.instructor:
            instr_id = schedule.instructor.instructorId # <--- FIX: Use unique ID as dictionary key
            instr_name = schedule.instructor.full_name
        else:
            instr_id = 'TBA_UNASSIGNED' 
            instr_name = 'Unknown Instructor'

        # Use the unique ID as the key for aggregation
        instructor_load[instr_id]["id"] = instr_id
        instructor_load[instr_id]["name"] = instr_name # Set the full_name for display
        
        # Check the isOvertime flag set by the scheduler
        if schedule.isOvertime: 
            instructor_load[instr_id]["overload_min"] += duration_minutes
        else:
            instructor_load[instr_id]["normal_min"] += duration_minutes
            
        day = schedule.dayOfWeek
        instructor_load[instr_id]["daily_spread"][day] += duration_minutes

    # Final calculations for Room Usage
    for data in room_usage.values():
        data["usage_hours"] = round(data["total_minutes"] / 60.0, 2)
    ordered_room_usage = dict(sorted(room_usage.items(), key=lambda item: item[1]["usage_hours"], reverse=True))

    DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    formatted_instructor_data = []
    
    # Final calculations for Instructor Load
    for instr_id, data in instructor_load.items(): 
        if instr_id == 'TBA_UNASSIGNED': # Exclude unassigned schedules from instructor load table
             continue 
             
        data["total_hours"] = round((data["normal_min"] + data["overload_min"]) / 60.0, 2)
        data["normal_hours"] = round(data["normal_min"] / 60.0, 2)
        data["overload_hours"] = round(data["overload_min"] / 60.0, 2)
        
        daily_list = []
        for day in DAYS_ORDER:
            daily_list.append({"day": day, "hours": round(data["daily_spread"].get(day, 0) / 60.0, 2)})
        data["daily_spread_list"] = daily_list
        formatted_instructor_data.append(data)

    ordered_instructor_load = sorted(formatted_instructor_data, key=lambda item: item["total_hours"], reverse=True)

    semesters = Semester.objects.all().order_by("-createdAt")
    
    context = {
        "current_semester_id": semester_id,
        "selected_semester": semester_id,
        
        "batch_choices": batch_choices,               
        "selected_batch_key": batch_key,              
        "current_schedule_status": current_display_status, 
        
        "can_finalize": batch_key == 'active', 
        "is_finalized": batch_key == 'finalized',
        "can_revert": batch_key not in ['active', 'finalized', 'none'], 
        
        "room_usage_data": ordered_room_usage,
        "instructor_load_data": ordered_instructor_load,
        "days_order": DAYS_ORDER, 
        "semesters": semesters,
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