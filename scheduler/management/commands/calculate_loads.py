from django.core.management.base import BaseCommand
from scheduling.models import Schedule
from core.models import Instructor
from datetime import datetime, time

NORMAL_PERIODS = [
    (time(8, 0), time(12, 0)),
    (time(13, 0), time(17, 0)),
]

def calculate_hours(start, end):
    return (datetime.combine(datetime.today(), end) -
            datetime.combine(datetime.today(), start)).total_seconds() / 3600

def is_weekend(day_name):
    return day_name in ["Saturday", "Sunday"]

def split_hours(day, start, end):
    total = calculate_hours(start, end)

    # Weekend = all overload
    if is_weekend(day):
        return 0, total

    normal = 0
    for p_start, p_end in NORMAL_PERIODS:
        overlap_start = max(start, p_start)
        overlap_end = min(end, p_end)
        if overlap_start < overlap_end:
            normal += calculate_hours(overlap_start, overlap_end)

    return normal, total - normal


class Command(BaseCommand):
    help = "Calculate teaching load hours for each instructor"

    def handle(self, *args, **kwargs):
        instructors = Instructor.objects.all()

        results = []

        for inst in instructors:
            normal_hours = 0
            overload_hours = 0

            schedules = Schedule.objects.filter(instructor=inst, status="active")

            # Skip if they shouldn't teach
            if inst.employmentType == "on-leave/retired":
                results.append((inst, "ERROR: on leave but has schedule"))
                continue

            for sched in schedules:
                n, o = split_hours(
                    sched.dayOfWeek, sched.startTime, sched.endTime
                )

                # Part-time logic: track but no pay limit
                if inst.employmentType == "overload":
                    normal_hours += 0
                    overload_hours += (n + o)
                else:
                    normal_hours += n
                    overload_hours += o

            # Permanent overload cap
            max_overload = None
            if inst.employmentType == "permanent":
                max_overload = 9 if getattr(inst, "designation", None) else 12

            results.append({
                "Instructor": inst.fullName,
                "Employment Type": inst.employmentType,
                "Normal Hours": round(normal_hours, 2),
                "Overload Hours": round(overload_hours, 2),
                "Max Allowed Overload": max_overload,
                "Overload Exceeded": (
                    max_overload is not None and overload_hours > max_overload
                )
            })

        # Pretty print
        self.stdout.write("\n=== Teaching Load Summary ===\n")
        for r in results:
            self.stdout.write(str(r))
        self.stdout.write("\n✅ Load calculation completed.\n")
