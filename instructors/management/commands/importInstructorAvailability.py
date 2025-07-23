import csv
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_time
from instructors.models import InstructorAvailability
from core.models import Instructor


class Command(BaseCommand):
    help = 'Import instructor availability from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']

        try:
            with open(csv_file, newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                for row in reader:
                    instructor_id = row['instructorId'].strip()
                    day = row['dayOfWeek'].strip()
                    start_time_str = row['startTime'].strip()
                    end_time_str = row['endTime'].strip()

                    try:
                        instructor = Instructor.objects.get(pk=instructor_id)
                    except Instructor.DoesNotExist:
                        self.stderr.write(self.style.ERROR(f"Instructor {instructor_id} not found. Skipping row."))
                        continue

                    start_time = parse_time(start_time_str)
                    end_time = parse_time(end_time_str)

                    if not start_time or not end_time:
                        self.stderr.write(self.style.ERROR(f"Invalid time format in row: {row}"))
                        continue

                    if start_time >= end_time:
                        self.stderr.write(self.style.ERROR(f"Start time must be before end time: {row}"))
                        continue

                    try:
                        availability, created = InstructorAvailability.objects.update_or_create(
                            instructor=instructor,
                            dayOfWeek=day,
                            startTime=start_time,
                            endTime=end_time,
                            defaults={}
                        )
                        action = "Created" if created else "Updated"
                        self.stdout.write(self.style.SUCCESS(f"{action} availability for {instructor_id} on {day} {start_time}-{end_time}"))

                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error saving row {row}: {e}"))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Unexpected error: {e}"))
