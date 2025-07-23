import csv
from django.core.management.base import BaseCommand
from scheduling.models import Subject, Curriculum

class Command(BaseCommand):
    help = 'Import subjects from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']

        try:
            with open(csv_file, newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    try:
                        curriculum_id = int(row['curriculumId'])
                        try:
                            curriculum = Curriculum.objects.get(pk=curriculum_id)
                        except Curriculum.DoesNotExist:
                            self.stderr.write(self.style.ERROR(f"Curriculum ID {curriculum_id} not found. Skipping row."))
                            continue

                        subject, created = Subject.objects.update_or_create(
                            code=row['code'].strip(),
                            defaults={
                                'curriculum': curriculum,
                                'name': row['name'].strip(),
                                'units': int(row['units']),
                                'durationMinutes': int(row['durationMinutes']),
                                'isPriorityForRooms': row['isPriorityForRooms'].strip().lower() == 'true',
                                'defaultTerm': int(row['defaultTerm']),
                                'yearLevel': int(row['yearLevel']),
                                'hasLab': row['hasLab'].strip().lower() == 'true',
                                'labDurationMinutes': int(row['labDurationMinutes']) if row['labDurationMinutes'].strip() else None,
                            }
                        )
                        action = "Created" if created else "Updated"
                        self.stdout.write(self.style.SUCCESS(f"{action} subject: {subject.code} - {subject.name}"))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error processing row: {row}. Error: {str(e)}"))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Unexpected error: {str(e)}"))
