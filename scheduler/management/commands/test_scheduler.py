# management/commands/test_scheduler.py
from django.core.management.base import BaseCommand
from scheduling.models import Semester, Schedule
from scheduler.solver import solve_schedule_for_semester
from scheduler.data_extractors import get_solver_data
from django.utils.timezone import datetime, make_aware
import datetime as dt

class Command(BaseCommand):
    help = "Test full scheduling for a semester and print Schedule outputs."

    def add_arguments(self, parser):
        parser.add_argument("semester_id", type=int, help="ID of semester to test")

    def handle(self, *args, **options):
        semester_id = options["semester_id"]
        semester = Semester.objects.get(pk=semester_id)

        print(f"Running scheduler test for semester: {semester}")

        # Extract solver data
        data = get_solver_data(semester)

        # Solve scheduling
        schedule_assignments = solve_schedule_for_semester(semester, time_limit_seconds=60)

        if not schedule_assignments:
            self.stdout.write(self.style.ERROR("No feasible solution found for scheduling."))
            return

        # Delete old schedules for semester
        Schedule.objects.filter(semester=semester).delete()

        # Map day int -> string
        day_map = {0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",4:"Friday"}

        # Save results to Schedule model
        schedules_to_create = []
        for entry in schedule_assignments:
            # Compute start and end times as time objects
            start_minute = entry["start_minute"]
            duration_min = entry["duration_min"]
            start_hour = start_minute // 60
            start_min = start_minute % 60

            start_time = dt.time(hour=start_hour, minute=start_min)
            end_minute = start_minute + duration_min
            end_hour = end_minute // 60
            end_min = end_minute % 60
            end_time = dt.time(hour=end_hour, minute=end_min)

            schedules_to_create.append(
                Schedule(
                    subject_id=entry.get("subject_id") or entry.get("subjectId"),
                    instructor_id=entry["instructor_id"],
                    section_id=entry["section_id"],
                    semester=semester,
                    room=None,  # Set to None (TBA) for now, or use your room assignment logic if implemented
                    dayOfWeek=day_map.get(entry["day"], "Monday"),
                    startTime=start_time,
                    endTime=end_time,
                    scheduleType=entry.get("scheduleType", "lecture"),  # default or based on input
                    isOvertime=start_hour >= 17,
                    status="active",
                )
            )

        Schedule.objects.bulk_create(schedules_to_create)

        self.stdout.write(self.style.SUCCESS(f"Saved {len(schedules_to_create)} schedules to DB."))

        # Output schedule summary
        for sched in Schedule.objects.filter(semester=semester).order_by("dayOfWeek", "startTime"):
            print(f"{sched.dayOfWeek} {sched.startTime.strftime('%H:%M')} - {sched.endTime.strftime('%H:%M')} | "
                  f"{sched.subject.code} | Section {sched.section.sectionCode} | Instructor {sched.instructor.user.get_full_name()} | Room: {sched.room or 'TBA'}")

