# scheduling/views.py
from django.shortcuts import render
from scheduling.models import Schedule, Semester
from core.models import Instructor, UserLogin
from django.contrib.auth.decorators import login_required
from collections import defaultdict

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