# scheduler/management/commands/check_hours.py
from django.core.management.base import BaseCommand
from scheduler.diagnostics import check_supply_vs_demand

class Command(BaseCommand):
    help = 'Checks if there are enough instructor hours to cover section demand.'

    def add_arguments(self, parser):
        # Optional: Allow passing a specific semester ID
        parser.add_argument(
            '--semester_id', 
            type=int, 
            help='The ID of the semester to check (optional)'
        )

    def handle(self, *args, **options):
        semester_id = options['semester_id']
        
        # Call the logic we defined in diagnostics.py
        check_supply_vs_demand(semester_id)