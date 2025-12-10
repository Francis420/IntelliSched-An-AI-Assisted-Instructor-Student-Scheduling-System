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
from datetime import datetime, time, timedelta
from django.utils import timezone
from authapi.views import has_role  
import re


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
    """
    Displays the logged-in instructor's schedule in a timetable matrix format.
    Shows Subject + Section (Year+Letter) + Room.
    """
    user = request.user
    
    # 1. Identify the Instructor
    login_entry = UserLogin.objects.filter(user=user).select_related("instructor").first()
    if not login_entry or not login_entry.instructor:
        return render(request, "scheduler/instructorSchedule.html", {
            "error": "No instructor profile found for this account."
        })

    instructor = login_entry.instructor

    # 2. Semester Selection Logic
    all_semesters = Semester.objects.order_by('-academicYear', 'term')
    semester_id = request.GET.get("semester")
    
    current_semester = None
    if semester_id:
        current_semester = all_semesters.filter(pk=semester_id).first()
    
    # Default to latest if not selected
    if not current_semester:
        current_semester = all_semesters.first()
        if current_semester:
            semester_id = str(current_semester.pk)

    if not current_semester:
         return render(request, "scheduler/instructorSchedule.html", {
            "error": "No semesters found in the system.",
            "instructor": instructor
        })

    # 3. Fetch Schedules (Filter by Instructor + Semester + Finalized)
    schedules = Schedule.objects.filter(
        instructor=instructor,
        semester=current_semester,
        status='finalized' # Show only official schedules
    ).select_related("subject", "section", "room")

    # 4. Prepare Timetable Matrix
    schedule_list = list(schedules)
    
    if not schedule_list:
        min_time = time(7, 0)
        max_time = time(19, 0)
    else:
        min_hour = min(s.startTime.hour for s in schedule_list)
        max_hour = max(s.endTime.hour for s in schedule_list)
        min_time = time(max(0, min_hour - 1), 0)
        max_time = time(min(23, max_hour + 1), 0)

    # Align start/end to 30 min intervals
    start_dt = datetime.combine(datetime.today(), min_time)
    if start_dt.minute >= 30:
        start_dt = start_dt.replace(minute=30, second=0, microsecond=0)
    else:
        start_dt = start_dt.replace(minute=0, second=0, microsecond=0)

    end_dt = datetime.combine(datetime.today(), max_time)
    if end_dt.minute > 30:
        end_dt = end_dt + timedelta(hours=1).replace(minute=0, second=0, microsecond=0)
    elif end_dt.minute > 0:
        end_dt = end_dt.replace(minute=30, second=0, microsecond=0)
    
    time_slots_display = []
    current_dt = start_dt
    while current_dt < end_dt:
        time_slots_display.append(current_dt.strftime('%I:%M %p'))
        current_dt += timedelta(minutes=30)
    
    DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    # Map: day -> slot -> [schedules]
    raw_data = defaultdict(lambda: defaultdict(list))

    for s in schedule_list:
        if s.dayOfWeek not in DAYS_OF_WEEK:
            continue
        
        sched_start_dt = datetime.combine(datetime.today(), s.startTime)
        sched_end_dt = datetime.combine(datetime.today(), s.endTime)
        if sched_end_dt < sched_start_dt:
             sched_end_dt += timedelta(days=1)
        
        # --- NEW SECTION LABEL LOGIC (Year + Section, e.g. "1B") ---
        subject_code = s.subject.code
        year_level = ""
        # 1. Extract Year (first digit in Subject Code)
        match_year = re.search(r'\d', subject_code)
        if match_year:
            year_level = match_year.group()
        
        # 2. Extract Section Letter (after last hyphen in Section Code)
        raw_section = s.section.sectionCode
        if '-' in raw_section:
            section_letter = raw_section.split('-')[-1].strip()
        else:
            section_letter = raw_section.strip()
            
        section_str = f"{year_level}{section_letter}" 
        # -----------------------------------------------------------

        subject_str = s.subject.code
        room_str = s.room.roomCode if s.room else "TBA"
        
        current_slot_dt = start_dt
        slot_index = 0
        
        while current_slot_dt < end_dt:
            slot_end_dt = current_slot_dt + timedelta(minutes=30)
            slot_time_str = time_slots_display[slot_index]

            if sched_start_dt < slot_end_dt and sched_end_dt > current_slot_dt:
                rowspan = int(s.duration_minutes / 30)
                
                raw_data[s.dayOfWeek][slot_time_str].append({
                    'subject': subject_str,
                    'section': section_str, # Now uses "1B" format
                    'room': room_str,
                    'start_time': s.startTime.strftime('%I:%M %p'),
                    'end_time': s.endTime.strftime('%I:%M %p'),
                    'rowspan': rowspan,
                    'height_px': rowspan * 40,
                    'is_start_slot': (sched_start_dt >= current_slot_dt and sched_start_dt < slot_end_dt) or (current_slot_dt == start_dt and sched_start_dt < start_dt)
                })
            
            current_slot_dt = slot_end_dt
            slot_index += 1

    # 5. Build Final Matrix Rows
    matrix = []
    for time_slot in time_slots_display:
        row_data = {'time': time_slot, 'days': []}
        for day in DAYS_OF_WEEK:
            schedules_in_cell = raw_data[day][time_slot]
            row_data['days'].append(schedules_in_cell)
        matrix.append(row_data)

    context = {
        "instructor": instructor,
        "semesters": all_semesters,
        "current_semester": current_semester,
        "matrix": matrix,
        "days_of_week": DAYS_OF_WEEK,
        "has_schedules": len(schedule_list) > 0
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


# ----- Room Utilization -----
@login_required
@has_role('deptHead')
def roomUtilization(request):
    # 1. Retrieve or Default Semester ID
    semester_id = request.GET.get("semester")
    if not semester_id:
        latest_semester = Semester.objects.order_by("-createdAt").first()
        if latest_semester:
            semester_id = str(latest_semester.semesterId)
        else:
            return render(request, "scheduler/roomUtilization.html", {"error": "No semesters found."})

    # 2. Get Filter Parameters (Room)
    selected_room_code = request.GET.get("room_code", "All")

    # 3. Fetch Data for Selectors
    all_rooms = Room.objects.all().order_by('roomCode')
    
    # 4. Fetch Schedules (Strictly FINALIZED)
    schedules = Schedule.objects.filter(
        semester__semesterId=semester_id,
        status='finalized'
    ).select_related(
        'room', 'subject', 'section'
    ).exclude(
        room__isnull=True 
    )

    if selected_room_code != "All":
        schedules = schedules.filter(room__roomCode=selected_room_code)

    # 5. Prepare Timetable Structure
    schedule_list = list(schedules) 
    
    if not schedule_list:
        min_time = time(7, 0)
        max_time = time(19, 0)
    else:
        min_hour = min(s.startTime.hour for s in schedule_list)
        max_hour = max(s.endTime.hour for s in schedule_list)
        min_time = time(max(0, min_hour - 1), 0)
        max_time = time(min(23, max_hour + 1), 0)

    start_dt = datetime.combine(datetime.today(), min_time)
    if start_dt.minute >= 30:
        start_dt = start_dt.replace(minute=30, second=0, microsecond=0)
    else:
        start_dt = start_dt.replace(minute=0, second=0, microsecond=0)

    end_dt = datetime.combine(datetime.today(), max_time)
    if end_dt.minute > 30:
        end_dt = end_dt + timedelta(hours=1).replace(minute=0, second=0, microsecond=0)
    elif end_dt.minute > 0:
        end_dt = end_dt.replace(minute=30, second=0, microsecond=0)
    
    time_slots_display = []
    current_dt = start_dt
    while current_dt < end_dt:
        time_slots_display.append(current_dt.strftime('%I:%M %p'))
        current_dt += timedelta(minutes=30)
    
    DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    raw_room_data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for s in schedule_list:
        if s.dayOfWeek not in DAYS_OF_WEEK:
            continue
        
        sched_start_dt = datetime.combine(datetime.today(), s.startTime)
        sched_end_dt = datetime.combine(datetime.today(), s.endTime)
        if sched_end_dt < sched_start_dt:
             sched_end_dt += timedelta(days=1)
        
        # --- NEW SECTION LABEL LOGIC ---
        # Goal: "1B" (Year 1, Section B)
        
        # 1. Extract Year from Subject Code (e.g. "IT 143" -> "1")
        subject_code = s.subject.code
        year_level = ""
        # Find the first digit in the subject code
        match_year = re.search(r'\d', subject_code)
        if match_year:
            year_level = match_year.group()
        
        # 2. Extract Section Letter from Section Code (e.g. "143-B" -> "B")
        raw_section = s.section.sectionCode
        if '-' in raw_section:
            # Take the part after the last hyphen (e.g., "B" from "IT 143-B")
            section_letter = raw_section.split('-')[-1].strip()
        else:
            # Fallback if no hyphen exists (e.g., just "B")
            section_letter = raw_section.strip()
            
        # Combine: "1" + "B" = "1B"
        section_label = f"{year_level}{section_letter}" 
        # -------------------------------
        
        current_slot_dt = start_dt
        slot_index = 0
        
        while current_slot_dt < end_dt:
            slot_end_dt = current_slot_dt + timedelta(minutes=30)
            slot_time_str = time_slots_display[slot_index]

            if sched_start_dt < slot_end_dt and sched_end_dt > current_slot_dt:
                rowspan = int(s.duration_minutes / 30)
                
                raw_room_data[s.room.roomCode][s.dayOfWeek][slot_time_str].append({
                    'subject_code': s.subject.code,
                    'section_label': section_label,  # Now uses the "1B" format
                    'start_time': s.startTime.strftime('%I:%M %p'),
                    'end_time': s.endTime.strftime('%I:%M %p'),
                    'rowspan': rowspan,
                    'height_px': rowspan * 40, 
                    'is_start_slot': (sched_start_dt >= current_slot_dt and sched_start_dt < slot_end_dt) or (current_slot_dt == start_dt and sched_start_dt < start_dt)
                })
            
            current_slot_dt = slot_end_dt
            slot_index += 1

    # 6. Finalize Data Structure
    final_room_data = []
    
    if selected_room_code != "All":
        rooms_to_process = [r for r in all_rooms if r.roomCode == selected_room_code]
    else:
        active_room_codes = sorted(raw_room_data.keys())
        rooms_to_process = [r for r in all_rooms if r.roomCode in active_room_codes]

    for room_obj in rooms_to_process:
        room_code = room_obj.roomCode
        
        matrix = []
        for time_slot in time_slots_display:
            row_data = {'time': time_slot, 'days': []}
            for day in DAYS_OF_WEEK:
                schedules_in_cell = raw_room_data[room_code][day][time_slot]
                row_data['days'].append(schedules_in_cell)
            matrix.append(row_data)
            
        final_room_data.append({
            'code': room_code,
            'name': room_obj.roomCode, 
            'capacity': room_obj.capacity,
            'type': room_obj.get_type_display(), 
            'matrix': matrix,
        })
    
    semesters = Semester.objects.all().order_by("-createdAt")

    context = {
        'current_semester_id': semester_id,
        'selected_room_code': selected_room_code,
        'all_rooms': all_rooms,
        'room_data': final_room_data,
        'days_of_week': DAYS_OF_WEEK,
        'semesters': semesters, 
    }

    return render(request, "scheduler/roomUtilization.html", context)