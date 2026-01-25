# scheduler/management/commands/test_scheduler.py
from django.core.management.base import BaseCommand
from scheduling.models import Semester, Schedule
from scheduler.solver import solve_schedule_for_semester
from django.utils import timezone

class Command(BaseCommand):
    help = "Test full scheduling for a semester and print Schedule outputs."

    def add_arguments(self, parser):
        parser.add_argument("semester_id", type=int, help="ID of semester to test")

    def handle(self, *args, **options):
        semester_id = options["semester_id"]
        semester = Semester.objects.get(pk=semester_id)

        print(f"Running scheduler test for semester: {semester}")

        # Run solver (this already saves to DB)
        solve_schedule_for_semester(semester, time_limit_seconds=3600)

        # Print saved schedules
        schedules = Schedule.objects.filter(semester=semester).order_by("dayOfWeek", "startTime")
        print(f"\n[Output] {schedules.count()} schedules found for {semester}:\n")

        self.stdout.write(self.style.SUCCESS("[Done] Schedule listing complete."))
