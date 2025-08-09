import logging
import datetime
from django.core.management.base import BaseCommand
from scheduling.models import Semester, Schedule, Section
from scheduler.data_extractors import get_solver_data
from scheduler.assignment_utils import prepare_assignments
from scheduler.solver import solve_schedule_for_semester

logger = logging.getLogger(__name__)

def minutes_to_time(minutes):
    hour = minutes // 60
    minute = minutes % 60
    return datetime.time(hour=hour, minute=minute)

class Command(BaseCommand):
    help = "Run the AI-assisted scheduler for a given semester."

    def add_arguments(self, parser):
        parser.add_argument(
            "semester_id",
            type=int,
            help="ID of the semester to schedule."
        )

    def handle(self, *args, **options):
        semester_id = options["semester_id"]

        try:
            semester = Semester.objects.get(id=semester_id)
        except Semester.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Semester ID {semester_id} does not exist."))
            return

        logger.info(f"Starting scheduler for {semester}")

        # Step 1: Extract data
        data = get_solver_data(semester)
        logger.info("Data extraction complete.")

        # Step 2: Prepare initial assignments (optional, depends on your pipeline)
        assignments = prepare_assignments(data)
        logger.info(f"Prepared {len(assignments)} assignments.")

        # Step 3: Apply constraints and solve
        solution = solve_schedule_for_semester(semester)
        if not solution:
            self.stderr.write(self.style.ERROR("No feasible solution found."))
            return
        logger.info("Solver finished successfully.")

        # Step 4: Save to DB safely
        self._save_solution(solution, semester)

        self.stdout.write(self.style.SUCCESS(f"Scheduling complete for {semester}"))

    def _save_solution(self, solution, semester):
        # Delete old schedules for this semester
        Schedule.objects.filter(semester=semester).delete()

        # Collect section IDs from solution
        section_ids = [entry["section_id"] for entry in solution]

        # Fetch sections with related subject to get subject_id
        sections = Section.objects.filter(id__in=section_ids).select_related('subject')
        section_subject_map = {sec.id: sec.subject_id for sec in sections}

        # Log any missing sections
        missing_sections = set(section_ids) - set(section_subject_map.keys())
        if missing_sections:
            logger.error(f"Missing Section(s) in DB for these IDs: {missing_sections}")

        schedules_to_create = []

        for entry in solution:
            section_id = entry["section_id"]
            subject_id = section_subject_map.get(section_id)
            if subject_id is None:
                logger.error(f"Skipping Schedule entry: Section {section_id} missing subject or not found in DB.")
                continue  # Skip saving to avoid IntegrityError

            start_time = minutes_to_time(entry["start_minute"])
            end_time = minutes_to_time(entry["start_minute"] + entry["duration_min"])

            schedules_to_create.append(
                Schedule(
                    semester=semester,
                    section_id=section_id,
                    instructor_id=entry["instructor_id"],
                    subject_id=subject_id,
                    room_id=entry.get("room_id"),
                    dayOfWeek=entry["day"],
                    startTime=start_time,
                    endTime=end_time,
                )
            )

        Schedule.objects.bulk_create(schedules_to_create)
        logger.info(f"Saved {len(schedules_to_create)} schedules for semester {semester}.")
