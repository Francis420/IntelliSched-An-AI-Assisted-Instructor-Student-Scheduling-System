import csv
import re
from django.core.management.base import BaseCommand
from instructors.models import InstructorExperience
from scheduling.models import Subject
from core.models import Instructor
from django.utils.dateparse import parse_date
from django.db import IntegrityError

class Command(BaseCommand):
    help = 'Import instructor experience records from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']

        try:
            with open(csv_file, newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    instructor_id = row['instructorId'].strip()
                    try:
                        instructor = Instructor.objects.get(pk=instructor_id)
                    except Instructor.DoesNotExist:
                        self.stderr.write(self.style.WARNING(f"Instructor {instructor_id} not found. Skipping."))
                        continue

                    try:
                        experience, created = InstructorExperience.objects.get_or_create(
                            instructor=instructor,
                            title=row['title'].strip(),
                            organization=row['organization'].strip(),
                            startDate=parse_date(row['startDate'].strip()),
                            defaults={
                                'endDate': parse_date(row['endDate'].strip()) if row['endDate'].strip() else None,
                                'description': row['description'].strip(),
                                'experienceType': row['experienceType'].strip(),
                                'isVerified': row['isVerified'].strip().lower() == 'true'
                            }
                        )

                        if not created:
                            self.stdout.write(self.style.NOTICE(f"Experience already exists for {instructor_id}: {experience.title} at {experience.organization}"))

                        # Add related subjects (by subjectId)
                        subject_ids = re.split(r'[;,]', row['relatedSubjects'])
                        subject_ids = [sid.strip() for sid in subject_ids if sid.strip()]
                        for sid in subject_ids:
                            try:
                                subject = Subject.objects.get(subjectId=int(sid))
                                experience.relatedSubjects.add(subject)
                            except (Subject.DoesNotExist, ValueError):
                                self.stderr.write(self.style.WARNING(
                                    f"Subject ID '{sid}' not found or invalid for instructor {instructor_id}. Skipping subject."))

                        experience.save()
                        action = "Created" if created else "Updated"
                        self.stdout.write(self.style.SUCCESS(f"{action} experience for {instructor_id}: {experience.title} at {experience.organization}"))

                    except IntegrityError:
                        self.stderr.write(self.style.WARNING(f"Duplicate entry or error for {instructor_id}: {row['title']} at {row['organization']}. Skipping."))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Unexpected error for {instructor_id}: {str(e)}"))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Unexpected error: {str(e)}"))
