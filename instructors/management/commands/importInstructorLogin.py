import csv
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import UserLogin, Role, Instructor
# Ensure these models exist in your instructors app
from instructors.models import (
    InstructorRank,
    InstructorDesignation,
    InstructorAcademicAttainment
)

User = get_user_model()

class Command(BaseCommand):
    help = "Import instructor logins from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file")

    def handle(self, *args, **kwargs):
        csv_file = kwargs["csv_file"]

        if not os.path.exists(csv_file):
            self.stdout.write(self.style.ERROR(f"File not found: {csv_file}"))
            return

        # 1. Ensure 'instructor' Role exists
        try:
            instructor_role = Role.objects.get(name="instructor")
        except Role.DoesNotExist:
            self.stdout.write(self.style.WARNING("Role 'instructor' not found. Creating it now..."))
            instructor_role = Role.objects.create(name="instructor", label="Instructor")

        with open(csv_file, mode="r", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            
            created_count = 0
            
            for row in reader:
                try:
                    # 2. Check for existing Instructor ID
                    if Instructor.objects.filter(instructorId=row["instructorId"]).exists():
                        self.stdout.write(self.style.WARNING(f"Skipping existing instructor ID: {row['instructorId']}"))
                        continue

                    # 3. Check for existing Username
                    if User.objects.filter(username=row["username"]).exists():
                        self.stdout.write(self.style.WARNING(f"Skipping existing username: {row['username']}"))
                        continue

                    # 4. Fetch Foreign Keys (Handle IDs safely)
                    rank = None
                    if row.get("rank"):
                        try:
                            rank = InstructorRank.objects.get(rankId=row["rank"])
                        except:
                            pass # Leave as None if not found

                    designation = None
                    if row.get("designation"):
                        try:
                            designation = InstructorDesignation.objects.get(designationId=row["designation"])
                        except:
                            pass

                    attainment = None
                    if row.get("academicAttainment"):
                        try:
                            attainment = InstructorAcademicAttainment.objects.get(attainmentId=row["academicAttainment"])
                        except:
                            pass

                    # 5. Create Instructor Profile
                    instructor = Instructor.objects.create(
                        instructorId=row["instructorId"],
                        rank=rank,
                        designation=designation,
                        academicAttainment=attainment,
                        employmentType=row["employmentType"],
                    )

                    # 6. Create User Account (Hashes Password automatically)
                    user = User.objects.create_user(
                        username=row["username"],
                        email=row["email"],
                        password=row["password"], # Plain text here becomes Hash in DB
                        firstName=row["firstName"],
                        lastName=row["lastName"],
                        middleInitial=row.get("middleInitial") or None,
                    )
                    
                    # 7. Assign Role
                    user.roles.add(instructor_role)

                    # 8. Link User to Instructor (UserLogin)
                    UserLogin.objects.create(
                        user=user,
                        instructor=instructor
                    )

                    self.stdout.write(self.style.SUCCESS(f"Imported: {row['username']}"))
                    created_count += 1

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error on row {row.get('username')}: {e}"))
            
            self.stdout.write(self.style.SUCCESS(f"\nImport Finished. Created {created_count} users."))