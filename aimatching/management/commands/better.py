from django.core.management.base import BaseCommand
from aimatching.matcher.run_matching import run_matching


class Command(BaseCommand):
    help = "Run AI instructor-subject matching for a given semester"

    def add_arguments(self, parser):
        parser.add_argument('--semester', type=int, required=True, help='Semester ID')
        parser.add_argument('--batch-id', type=str, help='Batch ID (optional)')

    def handle(self, *args, **options):
        semester_id = options['semester']
        batch_id = options.get('batch_id')
        results = run_matching(semester_id, batch_id=batch_id)
        self.stdout.write(self.style.SUCCESS(f"✅ Matching run completed for semester {semester_id}"))
        self.stdout.write(f"Generated {sum(len(r[1]) for r in results)} instructor-subject matches.")
