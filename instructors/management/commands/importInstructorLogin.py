# how to import py .\manage.py importInstructorLogin path\to\csv
# Example:
# py .\manage.py importInstructorLogin C:\Users\user\Desktop\IntelliSched-An-AI-Assisted-Instructor-Student-Scheduling-System\imports\InstructorLogin.csv

import csv
import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import UserLogin, Role, Instructor
from instructors.models import InstructorRank, InstructorDesignation, InstructorAcademicAttainment

User = get_user_model()

class Command(BaseCommand):
    help = "Import instructor logins from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']

        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"File not found: {csv_file}"))
            return

        try:
            instructor_role = Role.objects.get(name="instructor")
        except Role.DoesNotExist:
            self.stdout.write(self.style.ERROR("Role 'instructor' not found. Please create it first."))
            return

        with open(csv_file, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            for row in reader:
                try:
                    # Skip if Instructor exists
                    if Instructor.objects.filter(instructorId=row['instructorId']).exists():
                        self.stdout.write(self.style.WARNING(f"Skipping existing instructor: {row['instructorId']}"))
                        continue

                    # Skip if username/email exists
                    if User.objects.filter(username=row['username']).exists():
                        self.stdout.write(self.style.WARNING(f"Skipping existing username: {row['username']}"))
                        continue
                    if User.objects.filter(email=row['email']).exists():
                        self.stdout.write(self.style.WARNING(f"Skipping existing email: {row['email']}"))
                        continue

                    # Get FK objects
                    rank = InstructorRank.objects.get(rankId=row['rank']) if row['rank'] else None
                    designation = InstructorDesignation.objects.get(designationId=row['designation']) if row['designation'] else None
                    academicAttainment = InstructorAcademicAttainment.objects.get(attainmentId=row['academicAttainment']) if row['academicAttainment'] else None

                    # Create Instructor
                    instructor = Instructor.objects.create(
                        instructorId=row['instructorId'],
                        rank=rank,
                        designation=designation,
                        academicAttainment=academicAttainment,
                        employmentType=row['employmentType']
                    )

                    # Create User
                    user = User.objects.create_user(
                        username=row['username'],
                        email=row['email'],
                        password=row['password'],
                        firstName=row['firstName'],
                        lastName=row['lastName']
                    )
                    user.roles.add(instructor_role)

                    # Create UserLogin
                    UserLogin.objects.create(
                        user=user,
                        instructor=instructor
                    )

                    self.stdout.write(self.style.SUCCESS(f"Successfully imported: {row['username']}"))

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error importing row: {row}. Error: {e}"))
