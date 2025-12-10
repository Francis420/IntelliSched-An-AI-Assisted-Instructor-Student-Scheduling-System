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
            
        return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=finalized')
    return redirect('scheduleOutput')

@login_required
@has_role('deptHead')
def revertFinalizedSchedule(request, semester_id):
    if request.method == 'POST':
        try:
            semester = Semester.objects.get(semesterId=semester_id)
        except Semester.DoesNotExist:
            messages.error(request, "Semester not found.")
            return redirect(reverse('scheduleOutput'))

        try:
            with transaction.atomic():
                # Step 1: Find the schedules currently marked as 'finalized'
                finalized_schedules = Schedule.objects.filter(
                    semester=semester, 
                    status='finalized'
                )

                if finalized_schedules.exists():
                    # Step 2: Change status to 'active'
                    finalized_schedules.update(status='active')
                    messages.success(request, f"Schedule for {semester.name} has been **UNLOCKED**.")
                else:
                    messages.warning(request, "No finalized schedule found to unlock.")

        except Exception as e:
            messages.error(request, f"An error occurred while unlocking the schedule: {e}")

        return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=active')
    
    return redirect(reverse('scheduleOutput'))

@login_required
@has_role('deptHead')
def revertSchedule(request):
    if request.method == 'POST':
        semester_id = request.POST.get('semester_id')
        batch_key = request.POST.get('batch_key') 

        if not semester_id or not batch_key or batch_key in ['active', 'finalized']:
            messages.error(request, "Invalid request for schedule reversion.")
            return redirect(reverse('scheduleOutput'))
        
        # 1. Check if a finalized run currently exists for this semester
        finalized_run_exists = Schedule.objects.filter(
            semester__semesterId=semester_id, 
            status='finalized'
        ).exists()
        
        if finalized_run_exists:
            messages.error(request, "A schedule is currently **FINALIZED**. Please unlock it first.")
            return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=finalized')
        
        try:
            dt_obj = datetime.fromisoformat(batch_key)
            
            schedules_to_promote = Schedule.objects.filter(
                semester__semesterId=semester_id,
                status='archived',
                createdAt=dt_obj 
            ).select_related('semester')
            
            if not schedules_to_promote.exists():
                messages.error(request, "The specified archived schedule batch was not found.")
                return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=active')
            
            semester = schedules_to_promote.first().semester

            with transaction.atomic():
                Schedule.objects.filter(semester=semester, status='active').update(status='archived')
                schedules_to_promote.update(status='active')
                messages.success(request, f"Successfully reverted to schedule batch created at {batch_key}.")

        except ValueError:
            messages.error(request, "Invalid batch key format.")
        except Exception as e:
            messages.error(request, f"Error during reversion: {e}")
        
        return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=active')
    
    return redirect(reverse('scheduleOutput'))


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
            # Handle case where no semesters exist at all
            return render(request, "scheduler/scheduleOutput.html", {"error": "No semesters found."})

    
    batch_key = request.GET.get("batch_key", 'active') # batch_key defaults to 'active'
    
    # 1. Get all unique creation timestamps for archived schedules
    # We must first truncate/group by the second for reliable batch identification.
    raw_archived_datetimes = Schedule.objects.filter(
        semester__semesterId=semester_id, 
        status='archived'
    ).order_by('-createdAt').values_list('createdAt', flat=True).distinct()
    
    # Python grouping to ensure only one timestamp per second exists for a batch
    unique_batch_times = {}
    for dt in raw_archived_datetimes:
        truncated_dt_key = dt.replace(microsecond=0)
        if truncated_dt_key not in unique_batch_times:
            unique_batch_times[truncated_dt_key] = truncated_dt_key
            
    # Sorted list of unique batch datetimes
    archived_batch_times = sorted(unique_batch_times.keys(), reverse=True)

    archived_batches = [
        {'key': batch_time.isoformat(), 'label': f"Archived Run: {batch_time.strftime('%b %d, %Y %I:%M %p')}"} 
        for batch_time in archived_batch_times
    ]

    # --- BATCH SELECTION LOGIC ---
    
    # Determine if a finalized run exists for the current semester
    finalized_exists = Schedule.objects.filter(
        semester__semesterId=semester_id, 
        status='finalized'
    ).exists()

    schedules = Schedule.objects.none() # Initialize to an empty QuerySet
    current_status = 'N/A'
    
    if batch_key == 'finalized' and finalized_exists:
        schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='finalized')
        current_status = 'Finalized Schedule (Locked)'
    
    elif batch_key == 'active' or (batch_key == 'finalized' and not finalized_exists):
        # Default to active if requested or if finalized was requested but doesn't exist
        schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='active')
        current_status = 'Active Draft'

        # If no active schedules, try to load the latest archived batch
        if not schedules.exists() and archived_batches:
             try:
                 latest_batch_time_iso = archived_batches[0]['key']
                 # Ensure datetime is timezone-aware for filtering
                 latest_batch_time = datetime.fromisoformat(latest_batch_time_iso)
                 if latest_batch_time.tzinfo is None:
                     latest_batch_time = timezone.make_aware(latest_batch_time)

                 # Filter the database records using the 1-second range
                 schedules = Schedule.objects.filter(
                     semester__semesterId=semester_id, 
                     createdAt__gte=latest_batch_time,
                     createdAt__lt=latest_batch_time + timedelta(seconds=1),
                     status='archived'
                 )
                 current_status = archived_batches[0]['label']
                 batch_key = latest_batch_time_iso
                 messages.info(request, "Active draft not found. Displaying the latest archived run instead.")
             except Exception:
                 schedules = Schedule.objects.none()
                 current_status = 'No Schedules Found'
                 batch_key = 'none'


    elif batch_key:
        # Load a specific archived batch using the batch_key (timestamp)
        try:
            selected_timestamp = datetime.fromisoformat(batch_key)
            
            # Handle timezone if necessary
            if selected_timestamp.tzinfo is None:
                selected_timestamp = timezone.make_aware(selected_timestamp)
            
            # Truncate to the second to match grouping logic
            selected_timestamp = selected_timestamp.replace(microsecond=0)
            
            # Filter the database records using the 1-second range
            schedules = Schedule.objects.filter(
                semester__semesterId=semester_id, 
                createdAt__gte=selected_timestamp,
                createdAt__lt=selected_timestamp + timedelta(seconds=1),
                status='archived'
            )
            # Find the correct label for display
            label = next((b['label'] for b in archived_batches if b['key'] == batch_key), f"Archived Run ({selected_timestamp.strftime('%b %d, %I:%M %p')})")
            current_status = label

        except ValueError:
            messages.error(request, "Invalid schedule batch key provided. Falling back to active draft.")
            return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=active')
    
    # 2. Fetch Data with necessary lookups
    schedules = schedules.select_related(
        'instructor', 
        'room'
    ).prefetch_related(
        # This prefetch is necessary for schedule.instructor.full_name property
        'instructor__userlogin_set__user'
    ).order_by('dayOfWeek', 'startTime')
    
    # --- Aggregation Dictionaries Initialization and Logic ---
    DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    room_usage = defaultdict(lambda: {
        "room_code": None, 
        "total_minutes": 0, 
        "usage_hours": 0.0,
        "daily_spread": defaultdict(int) # Tracks daily usage in minutes
    })
    
    instructor_load = defaultdict(lambda: {
        "id": None, "name": None, "normal_min": 0, "overload_min": 0, "total_hours": 0.0,
        "daily_spread": defaultdict(int)
    })
    
    # Populate the aggregation dictionaries
    for schedule in schedules:
        # Assuming schedule.duration_minutes is a property on the Schedule model
        duration_minutes = schedule.duration_minutes 
        
        # Room Usage
        room_name = schedule.room.roomCode if schedule.room else "TBA"
        room_usage[room_name]["room_code"] = room_name
        room_usage[room_name]["total_minutes"] += duration_minutes
        
        # Track daily usage for rooms
        day = schedule.dayOfWeek
        room_usage[room_name]["daily_spread"][day] += duration_minutes
        
        # Instructor Load and Daily Spread 
        if schedule.instructor:
            instr_id = schedule.instructor.instructorId # Use unique ID as dictionary key
            instr_name = schedule.instructor.full_name # Assumes full_name is a property on Instructor
        else:
            instr_id = 'TBA_UNASSIGNED' 
            instr_name = 'Unassigned Sections'

        # Use the unique ID as the key for aggregation
        instructor_load[instr_id]["id"] = instr_id
        instructor_load[instr_id]["name"] = instr_name
        
        if schedule.isOvertime: 
            instructor_load[instr_id]["overload_min"] += duration_minutes
        else:
            instructor_load[instr_id]["normal_min"] += duration_minutes
            
        day = schedule.dayOfWeek
        instructor_load[instr_id]["daily_spread"][day] += duration_minutes

    # --- Final calculations and formatting for Room Usage ---
    formatted_room_data = [] 
    
    for room_code, data in room_usage.items():
        data["usage_hours"] = round(data["total_minutes"] / 60.0, 2)
        
        # Prepare daily spread list (in hours) for template
        daily_list = []
        for day in DAYS_ORDER:
            daily_list.append({"day": day, "hours": round(data["daily_spread"].get(day, 0) / 60.0, 2)})
        data["daily_spread_list"] = daily_list
        formatted_room_data.append(data)

    # Sort room usage descending by total hours
    ordered_room_usage = sorted(formatted_room_data, key=lambda item: item["usage_hours"], reverse=True)


    # --- Final calculations and formatting for Instructor Load ---
    formatted_instructor_data = []
    
    # Final calculations for Instructor Load
    for instr_id, data in instructor_load.items(): 
        if instr_id == 'TBA_UNASSIGNED': # Exclude the unassigned aggregation from the load table
            continue 
            
        data["total_hours"] = round((data["normal_min"] + data["overload_min"]) / 60.0, 2)
        data["normal_hours"] = round(data["normal_min"] / 60.0, 2)
        data["overload_hours"] = round(data["overload_min"] / 60.0, 2)
        
        # Prepare daily spread list for template/chart
        daily_list = []
        for day in DAYS_ORDER:
            daily_list.append({"day": day, "hours": round(data["daily_spread"].get(day, 0) / 60.0, 2)})
        data["daily_spread_list"] = daily_list
        formatted_instructor_data.append(data)

    # Sort instructor load descending by total hours
    ordered_instructor_load = sorted(formatted_instructor_data, key=lambda item: item["total_hours"], reverse=True)

    # Get all semesters for the dropdown
    semesters = Semester.objects.all().order_by("-createdAt")
    
    # Get the current semester object for its term display
    try:
        current_semester = Semester.objects.get(semesterId=semester_id)
    except Semester.DoesNotExist:
        current_semester = None


    context = {
        "current_semester_id": semester_id,
        "current_status": current_status,
        "batch_key": batch_key,
        "finalized_exists": finalized_exists,
        "schedules": schedules, # Keeping this here just in case, even though the table is removed
        "semesters": semesters,
        "archived_batches": archived_batches,
        "current_semester": current_semester,
        
        # Data for the metrics tables/charts
        "room_usage_data": ordered_room_usage, # NOTE: This is now a list of dicts, not dict of dicts
        "instructor_load_data": ordered_instructor_load,
        "days_order": DAYS_ORDER, 
        
        # Flags for action buttons (Can be used in scheduleOutput.html)
        "can_finalize": batch_key == 'active' and schedules.exists(), 
        "is_finalized": current_status.startswith('Finalized'),
        "can_revert": (batch_key not in ['active', 'finalized', 'none', 'N/A']) and schedules.exists(), 
    }
    return render(request, "scheduler/scheduleOutput.html", context)


# Individual Instructor Schedule View
@login_required
def instructorScheduleView(request):
    user = request.user
    login_entry = UserLogin.objects.filter(user=user).select_related("instructor").first()

    if not login_entry or not login_entry.instructor:
        return render(request, "scheduler/instructorSchedule.html", {
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