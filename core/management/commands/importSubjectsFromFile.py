from django.core.management.base import BaseCommand
from scheduling.models import Subject, Curriculum

class Command(BaseCommand):
    help = "Import subjects from a text file and assign them to a curriculum"

    def add_arguments(self, parser):
        parser.add_argument("filepath", type=str, help="Path to the .txt file containing subject data")
        parser.add_argument("--curriculumId", type=int, required=True, help="Curriculum ID to associate subjects with")

    def handle(self, *args, **options):
        filepath = options["filepath"]
        curriculum_id = options["curriculumId"]

        try:
            curriculum = Curriculum.objects.get(curriculumId=curriculum_id)
        except Curriculum.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Curriculum with ID {curriculum_id} does not exist."))
            return

        created, skipped = 0, 0

        with open(filepath, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 9:
                    self.stdout.write(self.style.WARNING(f"Skipped invalid line (needs 9 fields): {line}"))
                    skipped += 1
                    continue

                try:
                    code = parts[0]
                    name = parts[1]
                    units = int(parts[2])
                    duration = int(parts[3])
                    is_priority = bool(int(parts[4]))
                    default_term = int(parts[5])
                    year_level = int(parts[6])
                    has_lab = bool(int(parts[7]))
                    lab_duration = int(parts[8]) if has_lab else None

                    if Subject.objects.filter(code=code, curriculum=curriculum).exists():
                        skipped += 1
                        continue

                    Subject.objects.create(
                        curriculum=curriculum,
                        code=code,
                        name=name,
                        units=units,
                        durationMinutes=duration,
                        defaultTerm=default_term,
                        yearLevel=year_level,
                        hasLab=has_lab,
                        labDurationMinutes=lab_duration,
                        isPriorityForRooms=is_priority,
                        isActive=True
                    )
                    created += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error processing line: {line} -> {e}"))
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(f"Import finished. {created} created, {skipped} skipped."))
