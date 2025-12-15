# scheduler/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import transaction
from scheduling.models import Schedule, Semester, Section, Room, Curriculum
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
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.db.models import Sum
from weasyprint import HTML 
from django.template.loader import render_to_string
import math
from weasyprint import HTML, CSS
import openpyxl
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from django.conf import settings
from openpyxl.cell.cell import MergedCell
from copy import copy
from openpyxl.utils import get_column_letter
from openpyxl import load_workbook


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
            
            # Ensure the datetime object is timezone-aware
            if dt_obj.tzinfo is None:
                dt_obj = timezone.make_aware(dt_obj)
            
            # Fix: Use a range query to ignore microsecond differences
            schedules_to_promote = Schedule.objects.filter(
                semester__semesterId=semester_id,
                status='archived',
                createdAt__gte=dt_obj,
                createdAt__lt=dt_obj + timedelta(seconds=1)
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
            return render(request, "scheduler/scheduleOutput.html", {"error": "No semesters found."})

    # --- NEW LOGIC: Check for Finalized Schedule ---
    finalized_exists = Schedule.objects.filter(
        semester__semesterId=semester_id, 
        status='finalized'
    ).exists()

    raw_batch_key = request.GET.get("batch_key")

    # AUTO-REDIRECT: If finalized exists, and user is viewing 'active' (or default), redirect to 'finalized'
    if finalized_exists and (raw_batch_key is None or raw_batch_key == 'active'):
        return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=finalized')

    # Set default batch_key
    batch_key = raw_batch_key if raw_batch_key else 'active'
    
    # 2. Get all unique creation timestamps for archived schedules
    raw_archived_datetimes = Schedule.objects.filter(
        semester__semesterId=semester_id, 
        status='archived'
    ).order_by('-createdAt').values_list('createdAt', flat=True).distinct()
    
    unique_batch_times = {}
    for dt in raw_archived_datetimes:
        truncated_dt_key = dt.replace(microsecond=0)
        if truncated_dt_key not in unique_batch_times:
            unique_batch_times[truncated_dt_key] = truncated_dt_key
            
    archived_batch_times = sorted(unique_batch_times.keys(), reverse=True)

    archived_batches = [
        {'key': batch_time.isoformat(), 'label': f"Archived Run: {batch_time.strftime('%b %d, %Y %I:%M %p')}"} 
        for batch_time in archived_batch_times
    ]

    # --- BATCH SELECTION LOGIC ---
    schedules = Schedule.objects.none() 
    current_status = 'N/A'
    
    if batch_key == 'finalized' and finalized_exists:
        schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='finalized')
        current_status = 'Finalized Schedule (Locked)'
    
    elif batch_key == 'active':
        schedules = Schedule.objects.filter(semester__semesterId=semester_id, status='active')
        current_status = 'Active Draft'

        # Fallback: If no active schedules, try to load latest archived
        if not schedules.exists() and archived_batches:
             try:
                 latest_batch_time_iso = archived_batches[0]['key']
                 latest_batch_time = datetime.fromisoformat(latest_batch_time_iso)
                 if latest_batch_time.tzinfo is None:
                     latest_batch_time = timezone.make_aware(latest_batch_time)

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
        # Load specific archived batch
        try:
            selected_timestamp = datetime.fromisoformat(batch_key)
            if selected_timestamp.tzinfo is None:
                selected_timestamp = timezone.make_aware(selected_timestamp)
            selected_timestamp = selected_timestamp.replace(microsecond=0)
            
            schedules = Schedule.objects.filter(
                semester__semesterId=semester_id, 
                createdAt__gte=selected_timestamp,
                createdAt__lt=selected_timestamp + timedelta(seconds=1),
                status='archived'
            )
            # Find label
            label = next((b['label'] for b in archived_batches if b['key'] == batch_key), f"Archived Run ({selected_timestamp.strftime('%b %d, %I:%M %p')})")
            current_status = label

        except ValueError:
            messages.error(request, "Invalid schedule batch key provided. Falling back to active draft.")
            return redirect(reverse('scheduleOutput') + f'?semester={semester_id}&batch_key=active')
    
    # 3. Fetch Data
    schedules = schedules.select_related(
        'instructor', 'room'
    ).prefetch_related(
        'instructor__userlogin_set__user'
    ).order_by('dayOfWeek', 'startTime')
    
    # --- Aggregation Logic ---
    DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    room_usage = defaultdict(lambda: {
        "room_code": None, "total_minutes": 0, "usage_hours": 0.0,
        "daily_spread": defaultdict(int)
    })
    
    instructor_load = defaultdict(lambda: {
        "id": None, "name": None, "normal_min": 0, "overload_min": 0, "total_hours": 0.0,
        "daily_spread": defaultdict(int)
    })
    
    for schedule in schedules:
        duration_minutes = schedule.duration_minutes 
        
        # Room
        room_name = schedule.room.roomCode if schedule.room else "TBA"
        room_usage[room_name]["room_code"] = room_name
        room_usage[room_name]["total_minutes"] += duration_minutes
        room_usage[room_name]["daily_spread"][schedule.dayOfWeek] += duration_minutes
        
        # Instructor
        if schedule.instructor:
            instr_id = schedule.instructor.instructorId 
            instr_name = schedule.instructor.full_name
        else:
            instr_id = 'TBA_UNASSIGNED' 
            instr_name = 'Unassigned Sections'

        instructor_load[instr_id]["id"] = instr_id
        instructor_load[instr_id]["name"] = instr_name
        
        if schedule.isOvertime: 
            instructor_load[instr_id]["overload_min"] += duration_minutes
        else:
            instructor_load[instr_id]["normal_min"] += duration_minutes
            
        instructor_load[instr_id]["daily_spread"][schedule.dayOfWeek] += duration_minutes

    # Format Room Data
    formatted_room_data = [] 
    for room_code, data in room_usage.items():
        data["usage_hours"] = round(data["total_minutes"] / 60.0, 2)
        daily_list = []
        for day in DAYS_ORDER:
            daily_list.append({"day": day, "hours": round(data["daily_spread"].get(day, 0) / 60.0, 2)})
        data["daily_spread_list"] = daily_list
        formatted_room_data.append(data)
    ordered_room_usage = sorted(formatted_room_data, key=lambda item: item["usage_hours"], reverse=True)

    # Format Instructor Data
    formatted_instructor_data = []
    for instr_id, data in instructor_load.items(): 
        if instr_id == 'TBA_UNASSIGNED': 
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

    # Context
    semesters = Semester.objects.all().order_by("-createdAt")
    try:
        current_semester = Semester.objects.get(semesterId=semester_id)
    except Semester.DoesNotExist:
        current_semester = None

    context = {
        "current_semester_id": semester_id,
        "current_status": current_status,
        "batch_key": batch_key,
        "finalized_exists": finalized_exists,
        "schedules": schedules,
        "semesters": semesters,
        "archived_batches": archived_batches,
        "current_semester": current_semester,
        "room_usage_data": ordered_room_usage,
        "instructor_load_data": ordered_instructor_load,
        "days_order": DAYS_ORDER, 
        
        "can_finalize": (batch_key == 'active' and schedules.exists() and not finalized_exists),
        "is_finalized": current_status.startswith('Finalized'),
        "can_revert": (batch_key not in ['active', 'finalized', 'none', 'N/A']) and schedules.exists(), 
    }
    return render(request, "scheduler/scheduleOutput.html", context)


@login_required
def instructorScheduleView(request):
    """
    Displays the logged-in instructor's schedule in a timetable matrix format.
    Shows Subject + Section (Year+Letter) + Room + Type (Lec/Lab).
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
        status='finalized' 
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

    # --- COLOR PALETTE SETUP ---
    color_palette = [
        'bg-blue-600', 'bg-red-600', 'bg-emerald-600', 'bg-purple-600', 
        'bg-orange-600', 'bg-teal-600', 'bg-pink-600', 'bg-indigo-600', 
        'bg-cyan-600', 'bg-rose-600', 'bg-amber-600', 'bg-lime-600'
    ]
    section_color_map = {}
    color_index = 0
    # ---------------------------

    for s in schedule_list:
        if s.dayOfWeek not in DAYS_OF_WEEK:
            continue
        
        sched_start_dt = datetime.combine(datetime.today(), s.startTime)
        sched_end_dt = datetime.combine(datetime.today(), s.endTime)
        if sched_end_dt < sched_start_dt:
             sched_end_dt += timedelta(days=1)
        
        # --- SECTION LABEL LOGIC (Year + Section, e.g. "1B") ---
        subject_code = s.subject.code
        year_level = ""
        match_year = re.search(r'\d', subject_code)
        if match_year:
            year_level = match_year.group()
        
        raw_section = s.section.sectionCode
        if '-' in raw_section:
            section_letter = raw_section.split('-')[-1].strip()
        else:
            section_letter = raw_section.strip()
            
        section_str = f"{year_level}{section_letter}" 
        # -----------------------------------------------------------

        # --- DETERMINE TYPE (Lec/Lab) ---
        # Assuming model has a field 'type' or 'schedType'. 
        # Adjust 'getattr(s, "type", ...)' to match your actual model field name.
        raw_type = str(getattr(s, 'type', 'Lec')).lower() 
        type_label = "Lec"
        if "lab" in raw_type:
            type_label = "Lab"
        # --------------------------------

        # --- COLOR ASSIGNMENT LOGIC ---
        unique_key = f"{subject_code}_{section_str}"

        if unique_key not in section_color_map:
            section_color_map[unique_key] = color_palette[color_index % len(color_palette)]
            color_index += 1
        
        assigned_color_class = section_color_map[unique_key]
        assigned_hover_class = assigned_color_class.replace('600', '700')
        # ------------------------------

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
                    'section': section_str,
                    'room': room_str,
                    'type_label': type_label, # "Lec" or "Lab"
                    'start_time': s.startTime.strftime('%I:%M %p'),
                    'end_time': s.endTime.strftime('%I:%M %p'),
                    'rowspan': rowspan,
                    'height_px': rowspan * 40,
                    'is_start_slot': (sched_start_dt >= current_slot_dt and sched_start_dt < slot_end_dt) or (current_slot_dt == start_dt and sched_start_dt < start_dt),
                    
                    'color_class': assigned_color_class,
                    'hover_class': assigned_hover_class
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

    # --- COLOR PALETTE SETUP ---
    color_palette = [
        'bg-blue-600', 'bg-red-600', 'bg-emerald-600', 'bg-purple-600', 
        'bg-orange-600', 'bg-teal-600', 'bg-pink-600', 'bg-indigo-600', 
        'bg-cyan-600', 'bg-rose-600', 'bg-amber-600', 'bg-lime-600'
    ]
    section_color_map = {}
    color_index = 0

    for s in schedule_list:
        if s.dayOfWeek not in DAYS_OF_WEEK:
            continue
        
        sched_start_dt = datetime.combine(datetime.today(), s.startTime)
        sched_end_dt = datetime.combine(datetime.today(), s.endTime)
        if sched_end_dt < sched_start_dt:
             sched_end_dt += timedelta(days=1)
        
        # --- SECTION LABEL LOGIC ---
        subject_code = s.subject.code
        year_level = ""
        match_year = re.search(r'\d', subject_code)
        if match_year:
            year_level = match_year.group()
        
        raw_section = s.section.sectionCode
        if '-' in raw_section:
            section_letter = raw_section.split('-')[-1].strip()
        else:
            section_letter = raw_section.strip()
            
        section_label = f"{year_level}{section_letter}" 
        # ---------------------------

        # ### --- COLOR ASSIGNMENT LOGIC --- ###
        # Create unique key based on Subject Code + Section (e.g., "IT101_1B")
        unique_key = f"{subject_code} - {section_label}"

        if unique_key not in section_color_map:
            section_color_map[unique_key] = color_palette[color_index % len(color_palette)]
            color_index += 1
        
        assigned_color_class = section_color_map[unique_key]
        assigned_hover_class = assigned_color_class.replace('600', '700')
        # ----------------------------------------
        
        current_slot_dt = start_dt
        slot_index = 0
        
        while current_slot_dt < end_dt:
            slot_end_dt = current_slot_dt + timedelta(minutes=30)
            slot_time_str = time_slots_display[slot_index]

            if sched_start_dt < slot_end_dt and sched_end_dt > current_slot_dt:
                rowspan = int(s.duration_minutes / 30)
                
                raw_room_data[s.room.roomCode][s.dayOfWeek][slot_time_str].append({
                    'subject_code': s.subject.code,
                    'section_label': section_label,
                    'start_time': s.startTime.strftime('%I:%M %p'),
                    'end_time': s.endTime.strftime('%I:%M %p'),
                    'rowspan': rowspan,
                    'height_px': rowspan * 40, 
                    'is_start_slot': (sched_start_dt >= current_slot_dt and sched_start_dt < slot_end_dt) or (current_slot_dt == start_dt and sched_start_dt < start_dt),
                    
                    # Pass colors to template
                    'color_class': assigned_color_class,
                    'hover_class': assigned_hover_class
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


# PDF export
# Helper to merge multiple schedule blocks for the same subject/section
def format_number(num):
    try:
        f_num = float(num)
        if f_num.is_integer(): return int(f_num)
        return f_num
    except (ValueError, TypeError): return 0

def get_semester_text(term):
    mapping = {'1st': 'FIRST', '2nd': 'SECOND', 'Midyear': 'MIDYEAR'}
    return mapping.get(term, str(term).upper())

def get_short_day(day_full):
    mapping = {'Monday': 'M', 'Tuesday': 'T', 'Wednesday': 'W', 'Thursday': 'TH', 'Friday': 'F', 'Saturday': 'SAT', 'Sunday': 'SUN'}
    return mapping.get(day_full, day_full)

def get_instructor_involvement(instructor):
    """
    Calculates involvement hours based on Designation (priority) or Rank.
    """
    context = {
        'inv_admin': 0,
        'inv_research': 0,
        'inv_extension': 0,
        'inv_consultation': 0, # Instruction + Consultation (+ Adviser)
        'inv_others': 0,       # Production
    }

    if instructor.designation:
        d = instructor.designation
        context['inv_admin'] = d.adminSupervisionHours
        context['inv_research'] = d.researchHours
        context['inv_extension'] = d.extensionHours
        # Designation: Instruction + Consultation
        context['inv_consultation'] = d.instructionHours + d.consultationHours
        # Designation: Production -> Others
        context['inv_others'] = d.productionHours
    elif instructor.rank:
        r = instructor.rank
        context['inv_admin'] = 0 
        context['inv_research'] = r.researchHours
        context['inv_extension'] = r.extensionHours
        # Rank: Instruction + Consultation + Class Adviser
        context['inv_consultation'] = r.instructionHours + r.consultationHours + r.classAdviserHours
        # Rank: Production -> Others
        context['inv_others'] = r.productionHours

    return context

def format_section_time(section):
    """
    Formats time string based on available schedules.
    - Single Slot: "09:00-12:00" (Formal)
    - Multiple Slots: "9-12 / 1-3" (Compact)
    """
    # Get all schedules for this section (Lec, Lab, etc.)
    schedules = list(section.schedule_set.all())
    
    # Sort by day and time to keep order consistent
    # Assuming dayOfWeek uses full names, we might want a map, 
    # but standard sort is usually fine for grouping. 
    # Better to sort by startTime if days are equal.
    schedules.sort(key=lambda x: x.startTime)

    times = []
    use_compact = len(schedules) > 1  # Logic: Use compact format if > 1 slot

    for s in schedules:
        if use_compact:
            # Compact: "5" or "5:30" (No leading zero, no :00)
            def fmt(t):
                h = t.hour % 12 or 12
                # If minutes exist, show them. If 00, hide them.
                return f"{h}:{t.minute:02d}" if t.minute > 0 else f"{h}"
            
            t_str = f"{fmt(s.start_time)}-{fmt(s.end_time)}"
        else:
            # Standard: "05:00-08:00"
            def fmt_std(t):
                return t.strftime("%I:%M")
            t_str = f"{fmt_std(s.start_time)}-{fmt_std(s.end_time)}"
            
        times.append(t_str)

    return " / ".join(times) if times else "TBA"


def process_schedule_group(s_list):
    """Calculates Lec/Lab hours and formats row data with smart time formatting."""
    if not s_list: return None
    
    first = s_list[0]
    subject = first.subject
    
    # 1. Calculate Minutes/Hours
    lec_minutes = getattr(subject, 'durationMinutes', 0)
    lab_minutes = getattr(subject, 'labDurationMinutes', 0) if getattr(subject, 'hasLab', False) else 0
    
    total_lec_hours = lec_minutes / 60
    total_lab_hours = lab_minutes / 60

    # 2. Sort and Format Time/Days
    sorted_list = sorted(s_list, key=lambda x: (x.dayOfWeek, x.startTime))
    times, days = [], []
    
    # Check if we have multiple slots (e.g. Lec + Lab)
    use_compact = len(sorted_list) > 1

    for s in sorted_list:
        # --- TIME FORMATTING LOGIC ---
        if use_compact:
            # Compact: 5-8
            def fmt(t):
                h = t.hour % 12 or 12
                return f"{h}:{t.minute:02d}" if t.minute > 0 else f"{h}"
            t_str = f"{fmt(s.startTime)}-{fmt(s.endTime)}"
        else:
            # Formal: 05:00-08:00
            t_str = f"{s.startTime.strftime('%I:%M')}-{s.endTime.strftime('%I:%M')}"
        # -----------------------------

        times.append(t_str)
        days.append(get_short_day(s.dayOfWeek))

    time_str = " / ".join(times) 
    day_str = " / ".join(days)

    # 3. Section Formatting
    sec_obj = getattr(first, 'section', None)
    year_val = getattr(subject, 'yearLevel', '')
    if year_val is None: year_val = ""

    raw_sec = getattr(sec_obj, 'sectionCode', '') if sec_obj else ""
    if raw_sec:
        sec_letter = raw_sec.split('-')[-1].strip() if '-' in raw_sec else raw_sec.strip()
    else:
        sec_letter = "?" 

    formatted_section = f"BSIT {year_val}{sec_letter}"
    
    student_count = sec_obj.numberOfStudents if (sec_obj and hasattr(sec_obj, 'numberOfStudents')) else 0

    return {
        'code': subject.code,
        'description': subject.name,
        'units': format_number(subject.units),
        'time': time_str,
        'days': day_str,
        'lec': format_number(total_lec_hours) if total_lec_hours > 0 else "", 
        'lab': format_number(total_lab_hours) if total_lab_hours > 0 else 0,
        'students': student_count,
        'room': first.room.roomCode if (hasattr(first, 'room') and first.room) else "TBA",
        'section': formatted_section
    }

# ==========================================
# 2. EXCEL UTILS
# ==========================================

def safe_write(ws, row, col, value, align_center=False):
    """
    Safely writes to a cell. If the cell is merged, writes to the top-left cell.
    Optionally centers the text.
    """
    cell = ws.cell(row=row, column=col)
    target_cell = cell

    # Handle merged cells
    if isinstance(cell, MergedCell):
        for merged_range in ws.merged_cells.ranges:
            if cell.coordinate in merged_range:
                target_cell = ws.cell(row=merged_range.min_row, column=merged_range.min_col)
                break
    
    # Write Value
    target_cell.value = value
    
    # Apply Alignment if requested
    if align_center:
        target_cell.alignment = Alignment(horizontal='center', vertical='center')

def copy_row_style(ws, source_row_idx, target_row_idx):
    source_row = ws[source_row_idx]
    target_row = ws[target_row_idx]

    for src_cell, tgt_cell in zip(source_row, target_row):
        if src_cell.has_style:
            tgt_cell.font = copy(src_cell.font)
            tgt_cell.border = copy(src_cell.border)
            tgt_cell.fill = copy(src_cell.fill)
            tgt_cell.number_format = copy(src_cell.number_format)
            tgt_cell.protection = copy(src_cell.protection)
            tgt_cell.alignment = copy(src_cell.alignment)

def write_section_totals(ws, total_row_idx, data_rows, col_map):
    """
    Calculates sums for Units, Lec, Lab, and Students.
    Writes standard totals to the TOTAL row.
    Writes the GRAND TOTAL (Lec + Lab) to the row BELOW the Total row.
    """
    if not data_rows or not col_map:
        return

    # 1. Calculate Sums
    t_units = 0
    t_lec = 0
    t_lab = 0
    t_students = 0

    for row in data_rows:
        def val(k):
            v = row.get(k)
            try:
                if v is None or v == "": return 0
                return float(v)
            except (ValueError, TypeError):
                return 0
        
        t_units += val('units')
        t_lec += val('lec')
        t_lab += val('lab')
        t_students += val('students')

    # 2. Write STANDARD TOTALS to the "TOTAL" Row (total_row_idx)
    if 'units' in col_map:
        safe_write(ws, total_row_idx, col_map['units'], t_units, align_center=True)

    if 'lec' in col_map:
        safe_write(ws, total_row_idx, col_map['lec'], t_lec, align_center=True)
        
    if 'lab' in col_map:
        safe_write(ws, total_row_idx, col_map['lab'], t_lab, align_center=True)

    if 'students' in col_map:
        safe_write(ws, total_row_idx, col_map['students'], t_students, align_center=True)

    # 3. Write GRAND TOTAL (Lec + Lab) to the NEXT ROW (total_row_idx + 1)
    if 'lec' in col_map:
        grand_total = t_lec + t_lab
        # We write this into the 'lec' column on the row BELOW the totals
        safe_write(ws, total_row_idx + 1, col_map['lec'], grand_total, align_center=True)


def fill_list_section(ws, data_rows, start_search_row=1):
    """
    Fills data and finds the correct TOTAL row index.
    Returns: (total_row_idx, col_map)
    """
    # 1. Find the Template/Placeholder Row
    template_row_idx = None
    col_map = {} 

    for row in ws.iter_rows(min_row=start_search_row):
        possible_map = {}
        found_code = False
        for cell in row:
            if cell.value and isinstance(cell.value, str):
                val = cell.value.strip()
                possible_map[val.lower()] = cell.column
                if val == 'code': found_code = True
        
        if found_code:
            template_row_idx = row[0].row
            col_map = possible_map
            break
    
    # If no placeholder found, return inputs so we don't crash
    if not template_row_idx:
        return start_search_row, {}

    # If no data, we still need to find the Total row to return its position
    if not data_rows:
        # Scan down to find "TOTAL"
        for r_idx in range(template_row_idx + 1, template_row_idx + 20):
            # Check first few columns for "TOTAL"
            # Assuming TOTAL is in column B (index 2) based on your template
            cell_val = ws.cell(row=r_idx, column=2).value
            if cell_val and "TOTAL" in str(cell_val).upper():
                return r_idx, col_map
        return template_row_idx, col_map

    # 2. Prepare for Insertion
    num_to_insert = len(data_rows) - 1
    
    if num_to_insert > 0:
        merges_to_shift = []
        template_row_merges = []
        all_merges = list(ws.merged_cells.ranges)
        
        for merged_range in all_merges:
            if merged_range.min_row == template_row_idx and merged_range.max_row == template_row_idx:
                template_row_merges.append((merged_range.min_col, merged_range.max_col))
            elif merged_range.min_row > template_row_idx:
                merges_to_shift.append(merged_range)

        for m in merges_to_shift:
            ws.merged_cells.remove(m)

        ws.insert_rows(template_row_idx + 1, amount=num_to_insert)

        for m in merges_to_shift:
            new_min_row = m.min_row + num_to_insert
            new_max_row = m.max_row + num_to_insert
            ws.merge_cells(start_row=new_min_row, start_column=m.min_col,
                           end_row=new_max_row, end_column=m.max_col)

        for i in range(num_to_insert):
            target_row = template_row_idx + 1 + i
            copy_row_style(ws, template_row_idx, target_row)
            for min_col, max_col in template_row_merges:
                ws.merge_cells(start_row=target_row, start_column=min_col, 
                               end_row=target_row, end_column=max_col)

    # 3. Write Data
    for i, row_data in enumerate(data_rows):
        current_row = template_row_idx + i
        for key, val in row_data.items():
            key_lower = key.lower()
            if key_lower == 'lab' and (val is None or val == ""):
                val = 0

            if key_lower in col_map:
                col_idx = col_map[key_lower]
                safe_write(ws, current_row, col_idx, val)

    # 4. Find the TOTAL Row
    # Start searching immediately after the last data row
    last_data_row = template_row_idx + len(data_rows) - 1
    total_row_idx = None

    # Scan next 10 rows to find the word "TOTAL"
    for r_idx in range(last_data_row + 1, last_data_row + 10):
        # We check column 2 (B) or 1 (A) or search the row
        # Based on your template, "TOTAL" is in Column B
        val = ws.cell(row=r_idx, column=2).value 
        if val and "TOTAL" in str(val).upper():
            total_row_idx = r_idx
            break
    
    # If we couldn't find "TOTAL", default to the next row (fallback)
    if not total_row_idx:
        total_row_idx = last_data_row + 1

    return total_row_idx, col_map


@login_required
def previewWorkload(request):
    user = request.user
    instructor = None
    
    login_entry = UserLogin.objects.filter(user=user).select_related("instructor").first()
    if login_entry:
        instructor = login_entry.instructor

    # Semester & Curriculum
    semester_id = request.GET.get("semester")
    if semester_id:
        current_semester = Semester.objects.filter(pk=semester_id).first()
    else:
        current_semester = Semester.objects.order_by('-academicYear', 'term').first()

    curriculum = Curriculum.objects.filter(isActive=True).order_by('-createdAt').first()
    
    dept_head_obj = Instructor.objects.filter(designation__designationId=5).first()
    dept_head_name = dept_head_obj.full_name.upper() if dept_head_obj else "TBA"

    # --- INVOLVEMENT LOGIC (Use Helper) ---
    inv_context = get_instructor_involvement(instructor)
    
    # Extract values for the totals calculation
    admin_h = inv_context['inv_admin']
    research_h = inv_context['inv_research']
    extension_h = inv_context['inv_extension']
    instructional_h = inv_context['inv_consultation']
    
    # --- SCHEDULES ---
    all_schedules = Schedule.objects.filter(
        instructor=instructor,
        semester=current_semester,
        status='finalized'
    ).select_related('subject', 'section', 'room')

    reg_schedules_list = []
    over_schedules_list = []
    unique_sections = set()

    for s in all_schedules:
        unique_sections.add(s.section.sectionId)
        if s.isOvertime:
            over_schedules_list.append(s)
        else:
            reg_schedules_list.append(s)
            
    no_of_classes = len(unique_sections)

    def group_and_process(s_list):
        grouped = defaultdict(list)
        for s in s_list:
            key = (s.subject.subjectId, s.section.sectionId) 
            grouped[key].append(s)
        rows = []
        for key, group in grouped.items():
            processed = process_schedule_group(group)
            if processed:
                rows.append(processed)
        return rows

    regular_rows = group_and_process(reg_schedules_list)
    overload_rows = group_and_process(over_schedules_list)

    def sum_prop(rows, prop):
        total = 0
        for r in rows:
            val = r.get(prop, "")
            if val != "":
                try: total += float(val)
                except ValueError: pass
        return total

    # Totals
    total_involvement = sum([float(admin_h), float(research_h), float(extension_h), float(instructional_h)])
    
    involvement_data = {
        'admin': format_number(admin_h),
        'research': format_number(research_h),
        'extension': format_number(extension_h),
        'consultation': format_number(instructional_h),
        'total': format_number(total_involvement),
        'note_text': "COE GAD Coordinator" if float(admin_h) > 0 else "", 
        'no_of_classes': no_of_classes
    }

    context = {
        'instructor': instructor,
        'semester': current_semester,
        'semester_text': get_semester_text(current_semester.term) if current_semester else "",
        'curriculum': curriculum,
        'dept_head_name': dept_head_name,
        
        # Merge involvement keys directly for the template forms
        **inv_context, 
        
        'involvement_data': involvement_data,
        'regular_rows': regular_rows,
        'regular_totals': {
            'units': format_number(sum_prop(regular_rows, 'units')),
            'lec': format_number(sum_prop(regular_rows, 'lec')),
            'lab': format_number(sum_prop(regular_rows, 'lab')),
        },
        'overload_rows': overload_rows, 
        'overload_totals': {
            'units': format_number(sum_prop(overload_rows, 'units')),
            'lec': format_number(sum_prop(overload_rows, 'lec')),
            'lab': format_number(sum_prop(overload_rows, 'lab')),
        }
    }

    return render(request, 'scheduler/workload_preview.html', context)

@login_required
def exportWorkloadExcel(request):
    if request.method == "POST":
        template_path = os.path.join(settings.BASE_DIR, 'static', 'excel_templates', 'workload_template.xlsx')
        try:
            wb = load_workbook(template_path)
            ws = wb.active 
        except FileNotFoundError:
            return HttpResponse("Template file not found.", status=404)

        def to_number(val):
            if not val or val.strip() == "": return None 
            try:
                f = float(val)
                return int(f) if f.is_integer() else f
            except (ValueError, TypeError):
                return val 

        def extract_rows(prefix):
            codes = request.POST.getlist(f'{prefix}_code[]')
            titles = request.POST.getlist(f'{prefix}_title[]')
            units = request.POST.getlist(f'{prefix}_units[]')
            lecs = request.POST.getlist(f'{prefix}_lec[]')
            labs = request.POST.getlist(f'{prefix}_lab[]')
            students = request.POST.getlist(f'{prefix}_students[]')
            times = request.POST.getlist(f'{prefix}_time[]')
            days = request.POST.getlist(f'{prefix}_days[]')
            rooms = request.POST.getlist(f'{prefix}_room[]')
            sections = request.POST.getlist(f'{prefix}_section[]')
            
            rows = []
            for i in range(len(codes)):
                if codes[i].strip() or titles[i].strip(): 
                    rows.append({
                        'code': codes[i], 
                        'description': titles[i], 
                        'units': to_number(units[i]),    
                        'time': times[i], 
                        'days': days[i], 
                        'lec': to_number(lecs[i]),       
                        'lab': to_number(labs[i]),       
                        'students': to_number(students[i]), 
                        'room': rooms[i], 
                        'section': sections[i]
                    })
            return rows

        regular_rows = extract_rows('reg')
        overload_rows = extract_rows('over')

        faculty_name_raw = request.POST.get('header_faculty', 'INSTRUCTOR')
        
        variables = {
            'header_faculty': faculty_name_raw,
            'header_semester': request.POST.get('header_semester'),
            'header_rank': request.POST.get('header_rank'),
            'header_sy': request.POST.get('header_sy'),
            'header_college': request.POST.get('header_college'),
            'header_date': request.POST.get('header_date'),
            
            'inv_admin': to_number(request.POST.get('inv_admin', '')),
            'inv_research': to_number(request.POST.get('inv_research', '')),
            'nv_research': to_number(request.POST.get('inv_research', '')),
            'inv_extension': to_number(request.POST.get('inv_extension', '')),
            'inv_consultation': to_number(request.POST.get('inv_consultation', '')),
            'inv_others': to_number(request.POST.get('inv_others', '')), 
            'inv_classes': to_number(request.POST.get('inv_classes', '')),
            'inv_total': to_number(request.POST.get('inv_total', '')),
            'inv_note': request.POST.get('inv_note', ''),

            'sig_faculty': request.POST.get('sig_faculty'),
            'sig_dept_head': request.POST.get('sig_dept_head'),
            'sig_dean': request.POST.get('sig_dean'),
            'sig_vp': request.POST.get('sig_vp'),
            'sig_president': request.POST.get('sig_president'),
        }

        for row in ws.iter_rows():
            for cell in row:
                if cell.value in variables:
                    safe_write(ws, cell.row, cell.column, variables[cell.value])

        # --- Regular Section ---
        reg_total_row_idx, reg_col_map = fill_list_section(ws, regular_rows, start_search_row=1)
        if regular_rows and reg_col_map:
            write_section_totals(ws, reg_total_row_idx, regular_rows, reg_col_map)

        # --- Overload Section ---
        # Start search AFTER the Regular section's total row
        over_total_row_idx, over_col_map = fill_list_section(ws, overload_rows, start_search_row=reg_total_row_idx + 2)
        if overload_rows and over_col_map:
            write_section_totals(ws, over_total_row_idx, overload_rows, over_col_map)

        safe_name = faculty_name_raw.strip().replace(" ", "-").upper()
        filename = f"ACTUAL-TEACHING-LOAD-{safe_name}.xlsx"

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    return HttpResponse("Method not allowed")