from django.core.management.base import BaseCommand
from aimatching.pairText import trainBinaryMatchModel

class Command(BaseCommand):
    help = 'Train the binary classifier model for instructor–subject matching'

    def handle(self, *args, **kwargs):
        model = trainBinaryMatchModel()
        if model:
            self.stdout.write(self.style.SUCCESS("✅ Binary match model trained and saved successfully."))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Not enough training data. Skipping model training."))
