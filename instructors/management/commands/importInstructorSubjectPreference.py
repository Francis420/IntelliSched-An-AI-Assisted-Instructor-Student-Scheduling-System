import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from instructors.models import InstructorSubjectPreference
from core.models import Instructor
from scheduling.models import Subject

class Command(BaseCommand):
    help = 'Import instructor subject preferences from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def parse_datetime(self, value):
        value = value.strip()
        if not value:
            return datetime.now()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ValueError(f"Date format not recognized: {value}")

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']
        count = 0
        skipped = 0

        with open(csv_file, newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                instructor_id = row['instructorId'].strip()
                subject_id = row['subjectId'].strip()
                preference_type = row['preferenceType'].strip()
                reason = row['reason'].strip()
                created_at = self.parse_datetime(row.get('createdAt', ''))
                updated_at = self.parse_datetime(row.get('updatedAt', ''))

                instructor = Instructor.objects.filter(instructorId=instructor_id).first()
                if not instructor:
                    self.stdout.write(self.style.WARNING(f"Instructor {instructor_id} not found. Skipping."))
                    continue

                subject = Subject.objects.filter(subjectId=subject_id).first()
                if not subject:
                    self.stdout.write(self.style.WARNING(f"Subject {subject_id} not found. Skipping."))
                    continue

                if InstructorSubjectPreference.objects.filter(instructor=instructor, subject=subject).exists():
                    skipped += 1
                    continue

                InstructorSubjectPreference.objects.create(
                    instructor=instructor,
                    subject=subject,
                    preferenceType=preference_type,
                    reason=reason,
                    createdAt=created_at,
                    updatedAt=updated_at
                )

                count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Imported preference: {instructor_id} -> {subject.code} ({preference_type})"))

        self.stdout.write(self.style.SUCCESS(
            f"\nSuccessfully imported {count} preferences. Skipped {skipped} already existing."))
