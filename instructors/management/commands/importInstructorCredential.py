import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from instructors.models import InstructorCredentials
from core.models import Instructor
from scheduling.models import Subject

class Command(BaseCommand):
    help = 'Import instructor credentials from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']
        
        with open(csv_file, newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            count = 0
            skipped = 0

            for row in reader:
                instructor_id = row['instructorId'].strip()
                type = row['type'].strip()
                title = row['title'].strip()
                description = row['description'].strip()
                issuer = row['issuer'].strip()
                related_subject_ids = row['relatedSubjectIDs'].strip().split(';')
                is_verified = row['isVerified'].strip().upper() == 'TRUE'
                document_url = row['documentUrl'].strip() or None
                date_earned = datetime.strptime(row['dateEarned'].strip(), '%Y-%m-%d').date()

                instructor = Instructor.objects.filter(instructorId=instructor_id).first()
                if not instructor:
                    self.stdout.write(self.style.WARNING(f"Instructor {instructor_id} not found. Skipping."))
                    continue

                # ❗️Check if credential already exists (by instructor and title)
                existing = InstructorCredentials.objects.filter(
                    instructor=instructor,
                    title=title
                ).first()
                if existing:
                    self.stdout.write(self.style.NOTICE(f"Credential already exists for {instructor_id}: '{title}'. Skipping."))
                    skipped += 1
                    continue

                credential = InstructorCredentials.objects.create(
                    instructor=instructor,
                    type=type,
                    title=title,
                    description=description,
                    issuer=issuer,
                    isVerified=is_verified,
                    documentUrl=document_url,
                    dateEarned=date_earned
                )

                for subject_id in related_subject_ids:
                    subject_id = subject_id.strip()
                    if subject_id:
                        subject = Subject.objects.filter(subjectId=subject_id).first()
                        if subject:
                            credential.relatedSubjects.add(subject)
                        else:
                            self.stdout.write(self.style.WARNING(f"  Subject ID '{subject_id}' not found. Skipping."))

                credential.save()
                count += 1
                self.stdout.write(self.style.SUCCESS(f"Imported credential for {instructor_id}: '{title}'"))

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully imported {count} instructor credentials."))
        if skipped:
            self.stdout.write(self.style.NOTICE(f"{skipped} duplicates were skipped."))
