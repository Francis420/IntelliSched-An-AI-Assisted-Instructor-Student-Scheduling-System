from django.db import models
from core.models import Instructor
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError



# ---------- Instructor Experience ---------- 60/update views/templates to handle experienceType
# This model tracks the professional experiences of instructors, including work experience, academic positions, and research roles.
class InstructorExperience(models.Model):
    EXPERIENCE_TYPE_CHOICES = [
        ('Academic Position', 'Academic Position'),           # Professor, Lecturer, Dean
        ('Work Experience', 'Work Experience'),               # Industry-related roles
        ('Research Role', 'Research Role'),                   # Project Researcher, Lab Staff
        ('Administrative Role', 'Administrative Role'),       # Coordinator, Department Head
        ('Extension Service', 'Extension Service'),           # Community outreach, seminars
        ('Consultancy', 'Consultancy'),                       # External expert engagements
    ]

    experienceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    organization = models.CharField(max_length=100)
    startDate = models.DateField()
    endDate = models.DateField(null=True, blank=True)
    description = models.TextField()
    experienceType = models.CharField(max_length=30, choices=EXPERIENCE_TYPE_CHOICES)
    relatedSubjects = models.ManyToManyField('scheduling.Subject', blank=True)
    isVerified = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'title', 'organization', 'startDate')
        indexes = [
            models.Index(fields=['instructor', 'isVerified']),
        ]

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.title}"

    def is_current(self):
        # Returns True if the experience is ongoing (no endDate)
        return self.endDate is None

    def durationInMonths(self):
        # Returns duration of the experience in months
        from datetime import date
        end = self.endDate or date.today()
        return (end.year - self.startDate.year) * 12 + (end.month - self.startDate.month)
    
    def clean(self):
        if self.endDate and self.endDate < self.startDate:
            raise ValidationError("End date cannot be before start date.")








# ---------- Teaching History ---------- 60
# This model tracks the history of subjects taught by instructors, including the number of times taught.
# It will help in analyzing teaching patterns and subject expertise.
class TeachingHistory(models.Model):
    teachingId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE, related_name='teachingHistory')
    subject = models.ForeignKey('scheduling.Subject', on_delete=models.CASCADE)
    semester = models.ForeignKey('scheduling.Semester', on_delete=models.PROTECT, null=True)
    timesTaught = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'subject', 'semester')
        indexes = [
            models.Index(fields=['instructor', 'subject', 'semester']),
        ]

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.subject.code} ({self.semester}) x{self.timesTaught}"

    def incrementTimesTaught(self, count=1):
        if self.timesTaught + count < 0:
            raise ValueError("timesTaught cannot be negative.")
        self.timesTaught += count
        self.save()



# ---------- Instructor Credential ---------- 60
# This model stores various credentials that instructors have, such as certifications, workshops, and training.
class InstructorCredentials(models.Model):
    CREDENTIAL_TYPE_CHOICES = [
        ('License', 'License'),
        ('Certification', 'Certification'),
        ('Workshop', 'Workshop'),
        ('Seminar', 'Seminar'),
        ('Training', 'Training'),
        ('Short Course', 'Short Course'), 
    ]

    credentialId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    type = models.CharField(max_length=30, choices=CREDENTIAL_TYPE_CHOICES)
    title = models.CharField(max_length=100)
    description = models.TextField()
    issuer = models.CharField(max_length=100)
    relatedSubjects = models.ManyToManyField('scheduling.Subject', blank=True)
    isVerified = models.BooleanField(default=False)
    documentUrl = models.CharField(max_length=255, null=True, blank=True)
    dateEarned = models.DateField()
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['instructor', 'isVerified']),
        ]
        ordering = ['-dateEarned']

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.title}"


# ---------- Instructor Subject Preference ---------- 60 list all subjects, set all preferences to default "Neutral" then let the instructor update
# This model allows instructors to set their preferences for subjects they would like to teach.
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
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'subject')
        indexes = [
            models.Index(fields=['instructor', 'preferenceType']),
        ]
        ordering = ['instructor', 'subject']

    def is_preferred(self):
        return self.preferenceType == 'Prefer'

    def is_avoided(self):
        return self.preferenceType == 'Avoid'

    def __str__(self):
        return f"{self.instructor.instructorId} prefers {self.subject.code} ({self.preferenceType})"

    

# ---------- Instructor Designation ----------
# This model defines the designations available for instructors, including their workload allocations.
class InstructorDesignation(models.Model):
    designationId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)

    adminSupervisionHours = models.IntegerField(default=0)
    instructionHours = models.IntegerField(default=0)
    researchHours = models.IntegerField(default=0)
    extensionHours = models.IntegerField(default=0)
    productionHours = models.IntegerField(default=0)
    consultationHours = models.IntegerField(default=0)

    class Meta:
        ordering = ['designationId']
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name
    


# ---------- Instructor Rank ----------
# This model defines the ranks available for instructors, including their workload allocations.
class InstructorRank(models.Model):
    rankId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)

    instructionHours = models.IntegerField(default=0)
    researchHours = models.IntegerField(default=0)
    extensionHours = models.IntegerField(default=0)
    productionHours = models.IntegerField(default=0)
    consultationHours = models.IntegerField(default=0)
    classAdviserHours = models.IntegerField(default=0)

    class Meta:
        ordering = ['rankId']
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name
    


# ---------- Instructor Academic Attainment ----------
# This model defines the academic attainments of instructors and the corresponding allowed overloads.
class InstructorAcademicAttainment(models.Model):
    attainmentId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    suffix = models.CharField(max_length=10, blank=True, null=True)

    overloadUnitsHasDesignation = models.PositiveIntegerField()
    overloadUnitsNoDesignation = models.PositiveIntegerField() 

    class Meta:
        ordering = ['attainmentId']
        indexes = [
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return self.name



# ---------- Instructor Monitoring (Absences) ----------
# This model tracks instructor absences, both auto-detected and manually reported.
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
    


# ---------- Instructor Availability ---------- 35 still needs a better ui and implementation
# This model tracks the availability of instructors for scheduling purposes.
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
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'dayOfWeek', 'startTime', 'endTime')
        indexes = [
            models.Index(fields=['instructor', 'dayOfWeek']),
        ]
        ordering = ['instructor', 'dayOfWeek', 'startTime']

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.startTime >= self.endTime:
            raise ValidationError("Start time must be before end time.")

    def __str__(self):
        return f"{self.instructor.instructorId} - {self.dayOfWeek} {self.startTime}-{self.endTime}"