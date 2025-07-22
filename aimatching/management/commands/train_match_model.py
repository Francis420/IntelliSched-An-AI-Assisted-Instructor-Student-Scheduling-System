from django.core.management.base import BaseCommand
from aimatching.tfidf import trainTfidfSvmModel

class Command(BaseCommand):
    help = 'Train the TF-IDF + SVM model for instructor-subject matching'

    def handle(self, *args, **kwargs):
        model = trainTfidfSvmModel()
        if model:
            self.stdout.write(self.style.SUCCESS("✅ Model trained and saved successfully."))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Not enough training data. Skipping model training."))
