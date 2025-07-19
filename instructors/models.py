from django.db import models
from core.models import Instructor


# ---------- Instructor Experience ---------- 50
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
    relatedSubjects = models.ManyToManyField('scheduling.Subject', blank=True)
    isVerified = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.title}"


# ---------- Instructor Availability ---------- 25 still needs a better ui and implementation
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



# ---------- Teaching History ---------- 50
class TeachingHistory(models.Model):
    teachingId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey('scheduling.Subject', on_delete=models.CASCADE)

    semester = models.ForeignKey('scheduling.Semester', on_delete=models.PROTECT, null=True)

    timesTaught = models.PositiveIntegerField(default=1)

    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('instructor', 'subject', 'semester')

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.subject.code} ({self.semester}) x{self.timesTaught}"



# ---------- Instructor Credential ---------- 50
class InstructorCredentials(models.Model):
    CREDENTIAL_TYPE_CHOICES = [
        ('Certification', 'Certification'),
        ('Workshop', 'Workshop'),
        ('Training', 'Training'),
        ('License', 'License'),
    ]

    credentialId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    type = models.CharField(max_length=30, choices=CREDENTIAL_TYPE_CHOICES)
    title = models.CharField(max_length=100)
    description = models.TextField()
    relatedSubjects = models.ManyToManyField('scheduling.Subject', blank=True)
    isVerified = models.BooleanField(default=False)
    documentUrl = models.CharField(max_length=255, null=True, blank=True)
    dateEarned = models.DateField()
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.title}"


# ---------- Instructor Subject Preference ---------- 50 list all subjects, set all preferences to default "Neutral" then let the instructor update
class InstructorSubjectPreference(models.Model):
    PREFERENCE_TYPE_CHOICES = [
        ('Prefer', 'Prefer'),
        ('Neutral', 'Neutral'),
        ('Avoid', 'Avoid'),
    ]

    preferenceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey("scheduling.Subject", on_delete=models.CASCADE)
    preferenceType = models.CharField(max_length=20, choices=PREFERENCE_TYPE_CHOICES)
    reason = models.TextField(blank=True, null=True)
    updatedAt = models.DateTimeField(auto_now=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} prefers {self.subject.code} ({self.preferenceType})"


# ---------- Instructor Monitoring (Absences) ----------
class InstructorAbsence(models.Model):
    REPORT_TYPE_CHOICES = [
        ('auto-detected', 'Auto Detected'),
        ('manual', 'Manual'),
    ]

    absenceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    subject = models.ForeignKey("scheduling.Subject", on_delete=models.CASCADE)
    schedule = models.ForeignKey("scheduling.Schedule", on_delete=models.CASCADE)
    reportType = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    reason = models.TextField(blank=True, null=True)
    dateMissed = models.DateField()
    reportedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.instructor.instructorId} missed {self.subject.code} on {self.dateMissed}"
