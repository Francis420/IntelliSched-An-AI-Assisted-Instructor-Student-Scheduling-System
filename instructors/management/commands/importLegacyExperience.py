import csv
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from core.models import Instructor
from instructors.models import InstructorLegacyExperience 
from scheduling.models import Subject

class Command(BaseCommand):
    help = 'Import instructor legacy experience (subjects handled) from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']

        self.stdout.write(self.style.WARNING(f"Starting import from {csv_file}..."))

        try:
            with open(csv_file, newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                success_count = 0
                skip_count = 0

                for row in reader:
                    username = row['instructor_username'].strip()
                    subject_code = row['subject_code'].strip()

                    # 1. Find Instructor by Username (Through UserLogin)
                    try:
                        # FIX: Use double underscore to lookup via the UserLogin -> User relationship
                        instructor = Instructor.objects.get(userlogin__user__username=username)
                    except Instructor.DoesNotExist:
                        self.stderr.write(self.style.WARNING(f"Instructor with username '{username}' not found. Skipping."))
                        skip_count += 1
                        continue
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error finding instructor '{username}': {e}"))
                        skip_count += 1
                        continue

                    # 2. Find Subject by Code
                    try:
                        subject = Subject.objects.get(code=subject_code)
                    except Subject.DoesNotExist:
                        self.stderr.write(self.style.WARNING(f"Subject '{subject_code}' not found. Skipping."))
                        skip_count += 1
                        continue

                    # 3. Create or Update Legacy Experience
                    try:
                        experience, created = InstructorLegacyExperience.objects.update_or_create(
                            instructor=instructor,
                            subject=subject,
                            defaults={
                                'priorTimesTaught': int(row.get('priorTimesTaught', 1)),
                                'priorYearsExperience': float(row.get('priorYearsExperience', 1.0)),
                                'lastTaughtYear': int(row.get('lastTaughtYear', 2025)),
                                'remarks': row.get('remarks', 'Imported via management command')
                            }
                        )

                        action = "Created" if created else "Updated"
                        self.stdout.write(self.style.SUCCESS(f"{action}: {username} -> {subject_code}"))
                        success_count += 1

                    except IntegrityError:
                        self.stderr.write(self.style.WARNING(f"Database integrity error for {username} - {subject_code}. Skipping."))
                        skip_count += 1
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Unexpected error for {username}: {str(e)}"))
                        skip_count += 1

            self.stdout.write(self.style.SUCCESS(f"\nImport Finished. Success: {success_count}, Skipped/Error: {skip_count}"))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Critical error: {str(e)}"))