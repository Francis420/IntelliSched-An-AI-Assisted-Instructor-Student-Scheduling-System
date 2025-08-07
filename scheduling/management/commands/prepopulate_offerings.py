from django.core.management.base import BaseCommand
from scheduling.models import Subject, Semester, SubjectOffering

class Command(BaseCommand):
    help = "Prepopulate SubjectOffering for the active semester"

    def handle(self, *args, **options):
        try:
            semester = Semester.objects.get(isActive=True)
        except Semester.DoesNotExist:
            self.stdout.write(self.style.ERROR("No active semester found."))
            return

        subjects = Subject.objects.filter(isActive=True)
        count_created = 0

        for subject in subjects:
            offering, created = SubjectOffering.objects.get_or_create(
                subject=subject,
                semester=semester,
                defaults={"numberOfSections": 6, "status": "active"}
            )
            if created:
                count_created += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Created offering for {subject.code} in {semester.name}"
                ))
            else:
                self.stdout.write(f"Offering already exists for {subject.code} in {semester.name}")

        self.stdout.write(self.style.SUCCESS(
            f"Prepopulation complete: {count_created} new offerings created for {semester.name}"
        ))
