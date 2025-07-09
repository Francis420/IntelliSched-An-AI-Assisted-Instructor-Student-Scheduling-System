from django.db import models
from core.models import User, Department
from django.utils import timezone


# ---------- Instructor ----------
class Instructor(models.Model):
    instructorId = models.CharField(primary_key=True, max_length=20)  # e.g., 2025-123456
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    employmentType = models.CharField(max_length=20, choices=[('permanent', 'Permanent'), ('temporary', 'Temporary')])

    def __str__(self):
        return f"{self.instructorId} - {self.user.lastName}, {self.user.firstName}"


# ---------- Instructor Availability ----------
class InstructorAvailability(models.Model):
    AVAIL_DAYS = [
        ('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday')
    ]

    availabilityId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    dayOfWeek = models.CharField(max_length=10, choices=AVAIL_DAYS)
    startTime = models.TimeField()
    endTime = models.TimeField()

    def __str__(self):
        return f"{self.instructor.instructorId} | {self.dayOfWeek} {self.startTime}-{self.endTime}"


# ---------- Instructor Experience ----------
class InstructorExperience(models.Model):
    EXPERIENCE_TYPE = [
        ('Work Experience', 'Work Experience'),
        ('Award', 'Award'),
        ('Certification', 'Certification'),
        ('Research', 'Research'),
    ]

    experienceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    organization = models.CharField(max_length=100)
    startDate = models.DateField()
    endDate = models.DateField(blank=True, null=True)
    description = models.TextField()
    isSubjectRelated = models.BooleanField(default=False)
    isVerified = models.BooleanField(default=False)
    type = models.CharField(max_length=30, choices=EXPERIENCE_TYPE)
    documentUrl = models.CharField(max_length=255, blank=True, null=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.title} at {self.organization}"


# ---------- Teaching History ----------
class TeachingHistory(models.Model):
    SEMESTER_CHOICES = [
        ('1st', '1st'),
        ('2nd', '2nd'),
        ('Summer', 'Summer')
    ]

    teachingId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey('scheduling.Subject', on_delete=models.CASCADE)
    schedule = models.ForeignKey('scheduling.Schedule', on_delete=models.CASCADE)
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    schoolYear = models.CharField(max_length=20)  # e.g., "2025–2026"

    def __str__(self):
        return f"{self.instructor.instructorId} taught {self.subject.subjectCode} ({self.semester} {self.schoolYear})"
