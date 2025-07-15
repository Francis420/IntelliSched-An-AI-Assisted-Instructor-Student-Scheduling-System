from django.db import models
from core.models import Instructor
from scheduling.models import Subject, Schedule


# ---------- Instructor Experience ----------
class InstructorExperience(models.Model):
    EXPERIENCE_TYPE_CHOICES = [
        ('Work Experience', 'Work Experience'),
        ('Academic Position', 'Academic Position'),
        ('Research Role', 'Research Role')
    ]

    experienceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    organization = models.CharField(max_length=100)
    startDate = models.DateField()
    endDate = models.DateField(null=True, blank=True)
    description = models.TextField()
    type = models.CharField(max_length=30, choices=EXPERIENCE_TYPE_CHOICES)
    isVerified = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.title}"


# ---------- Instructor Availability ----------
class InstructorAvailability(models.Model):
    DAY_CHOICES = [
        ('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]

    availabilityId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    dayOfWeek = models.CharField(max_length=10, choices=DAY_CHOICES)
    startTime = models.TimeField()
    endTime = models.TimeField()
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.dayOfWeek} {self.startTime}-{self.endTime}"


# ---------- Teaching History ----------
class TeachingHistory(models.Model):
    teachingId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.subject.code}"


# ---------- Instructor Credential ----------
class InstructorCredentials(models.Model):
    CREDENTIAL_TYPE_CHOICES = [
        ('Certification', 'Certification'),
        ('Workshop', 'Workshop'),
        ('Training', 'Training'),
        ('License', 'License'),
    ]

    credentialId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    type = models.CharField(max_length=30, choices=CREDENTIAL_TYPE_CHOICES)
    title = models.CharField(max_length=100)
    description = models.TextField()
    isVerified = models.BooleanField(default=False)
    documentUrl = models.CharField(max_length=255, null=True, blank=True)
    dateEarned = models.DateField()
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.title}"


# ---------- Instructor Subject Preference ----------
class InstructorSubjectPreference(models.Model):
    PREFERENCE_TYPE_CHOICES = [
        ('Prefer', 'Prefer'),
        ('Neutral', 'Neutral'),
        ('Avoid', 'Avoid'),
    ]

    preferenceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    preferenceType = models.CharField(max_length=20, choices=PREFERENCE_TYPE_CHOICES)
    reason = models.TextField(blank=True, null=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} prefers {self.subject.code} ({self.preferenceType})"
