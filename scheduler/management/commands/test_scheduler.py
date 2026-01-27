# scheduler/management/commands/test_scheduler.py
from django.core.management.base import BaseCommand
from scheduling.models import Semester, Schedule
from scheduler.solver import solve_schedule_for_semester
from django.utils import timezone

class Command(BaseCommand):
    help = "Test full scheduling for a semester and print Schedule outputs."

    def add_arguments(self, parser):
        parser.add_argument("semester_id", type=int, help="ID of semester to test")
        
        parser.add_argument(
            "--time", 
            type=int, 
            default=3600, 
            help="Time limit in seconds (default 3600)"
        )

    def handle(self, *args, **options):
        semester_id = options["semester_id"]
        time_limit = options["time"]
        
        semester = Semester.objects.get(pk=semester_id)

        print(f"Running scheduler test for semester: {semester}")
        print(f"Time limit set to: {time_limit} seconds")

        solve_schedule_for_semester(semester, time_limit_seconds=time_limit)

        schedules = Schedule.objects.filter(semester=semester).order_by("dayOfWeek", "startTime")
        print(f"\n[Output] {schedules.count()} schedules found for {semester}:\n")

        self.stdout.write(self.style.SUCCESS("[Done] Schedule listing complete."))