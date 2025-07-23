import csv
from django.core.management.base import BaseCommand
from instructors.models import TeachingHistory
from core.models import Instructor
from scheduling.models import Subject, Semester

class Command(BaseCommand):
    help = "Import teaching history for instructors from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **kwargs):
        csv_file_path = kwargs['csv_file']

        try:
            with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                count = 0
                for row in reader:
                    instructor_id = row['instructorId'].strip()
                    subject_id = row['subjectId'].strip()
                    semester_id = row['semesterId'].strip()
                    times_taught = int(row['timesTaught'].strip())

                    try:
                        instructor = Instructor.objects.get(pk=instructor_id)
                    except Instructor.DoesNotExist:
                        self.stderr.write(f"Instructor ID '{instructor_id}' not found. Skipping row.")
                        continue

                    try:
                        subject = Subject.objects.get(pk=subject_id)
                    except Subject.DoesNotExist:
                        self.stderr.write(f"Subject ID '{subject_id}' not found. Skipping row.")
                        continue

                    try:
                        semester = Semester.objects.get(pk=semester_id)
                    except Semester.DoesNotExist:
                        self.stderr.write(f"Semester ID '{semester_id}' not found. Skipping row.")
                        continue

                    teaching_history, created = TeachingHistory.objects.get_or_create(
                        instructor=instructor,
                        subject=subject,
                        semester=semester,
                        defaults={'timesTaught': times_taught}
                    )

                    if not created:
                        teaching_history.incrementTimesTaught(times_taught)

                    count += 1

                self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} teaching history records."))

        except FileNotFoundError:
            self.stderr.write(f"File not found: {csv_file_path}")
        except Exception as e:
            self.stderr.write(f"Unexpected error: {str(e)}")
