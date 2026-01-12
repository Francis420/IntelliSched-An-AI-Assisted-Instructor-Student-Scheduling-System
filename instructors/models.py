#instructors\models.py
from django.db import models
from core.models import Instructor
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError



# ---------- Instructor Experience ----------
class InstructorExperience(models.Model):
    EXPERIENCE_TYPE_CHOICES = [
        ('Academic Position', 'Academic Position'),
        ('Industry', 'Industry/Work Experience'),
        ('Research Role', 'Research Role'),
        ('Administrative Role', 'Administrative Role'),
        ('Consultancy', 'Consultancy'),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ('FT', 'Full Time'),
        ('PT', 'Part Time'),
        ('CT', 'Contractual'),
    ]

    experienceId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE, related_name='experiences')
    
    title = models.CharField(max_length=100)
    organization = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)
    
    startDate = models.DateField()
    endDate = models.DateField(null=True, blank=True)
    isCurrent = models.BooleanField(default=False)

    description = models.TextField(blank=True)
    
    experienceType = models.CharField(max_length=30, choices=EXPERIENCE_TYPE_CHOICES)
    employmentType = models.CharField(max_length=2, choices=EMPLOYMENT_TYPE_CHOICES, default='FT')
    
    relatedSubjects = models.ManyToManyField('scheduling.Subject', blank=True)
    
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-startDate']
        indexes = [
            models.Index(fields=['instructor', 'experienceType']),
        ]

    def clean(self):
        if self.endDate and self.endDate < self.startDate:
            raise ValidationError("End date cannot be before start date.")

    def save(self, *args, **kwargs):
        self.isCurrent = (self.endDate is None)
        super().save(*args, **kwargs)
        

class TeachingAssignment(models.Model):
    """
    AUTO-GENERATED: Represents one specific SECTION taught in one specific semester.
    Populated automatically when a Schedule is marked as 'finalized'.
    """
    assignmentId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE, related_name='system_assignments')
    subject = models.ForeignKey('scheduling.Subject', on_delete=models.CASCADE)
    semester = models.ForeignKey('scheduling.Semester', on_delete=models.CASCADE)
    section = models.ForeignKey('scheduling.Section', on_delete=models.CASCADE)
    
    # Sum of hours from Schedule (e.g., 3.0 hrs)
    totalTeachingHours = models.DecimalField(max_digits=6, decimal_places=2, default=0.0)
    
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ensures we don't count the same section twice for the same person
        unique_together = ('instructor', 'subject', 'semester', 'section')
        verbose_name = "Automated Teaching Assignment Tracking"

    def __str__(self):
        return f"{self.subject.code} - {self.section} ({self.semester})"


class InstructorLegacyExperience(models.Model):
    """
    USER-ENTERED: Populated manually to account for history before this system existed.
    """
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE, related_name='legacy_experiences')
    subject = models.ForeignKey('scheduling.Subject', on_delete=models.CASCADE)
    
    # The "Starting Stats"
    priorTimesTaught = models.PositiveIntegerField(default=0, help_text="Count of sections handled before system usage")
    priorYearsExperience = models.DecimalField(max_digits=4, decimal_places=1, default=0, help_text="Years of experience before system usage")
    
    lastTaughtYear = models.IntegerField(null=True, blank=True, help_text="Year most recently taught (legacy)")
    remarks = models.TextField(blank=True, help_text="Context (e.g., 'Taught at Previous University')")
    
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('instructor', 'subject')
        verbose_name = "Legacy/Manual Experience"

    def __str__(self):
        return f"{self.instructor} - Legacy {self.subject.code}"


# ---------- Instructor Credential ---------- 60
class InstructorCredentials(models.Model):
    CREDENTIAL_TYPE_CHOICES = [
        ('PhD', 'Doctorate Degree'),
        ('Masters', 'Masters Degree'),
        ('Bachelors', 'Bachelors Degree'),
        ('License', 'Professional License'),
        ('Certification', 'Industry Certification'),
        ('Training', 'Training/Workshop'),
    ]

    credentialId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE, related_name='credentials')
    
    credentialType = models.CharField(max_length=30, choices=CREDENTIAL_TYPE_CHOICES)
    title = models.CharField(max_length=150)
    issuer = models.CharField(max_length=150)
    
    relatedSubjects = models.ManyToManyField('scheduling.Subject', blank=True) 
    
    dateEarned = models.DateField()
    expirationDate = models.DateField(null=True, blank=True)
    
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-dateEarned']

    def __str__(self):
        return f"{self.instructor_id} - {self.title}"
    

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

    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Instructor Designation"
        verbose_name_plural = "Instructor Designations"
        ordering = ['designationId']

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

    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Instructor Rank"
        verbose_name_plural = "Instructor Ranks"
        ordering = ['rankId']

    def __str__(self):
        return self.name
    


# ---------- Instructor Academic Attainment ----------
# This model defines the academic attainments of instructors and the corresponding allowed overloads.
class InstructorAcademicAttainment(models.Model):
    attainmentId = models.AutoField(primary_key=True) 
    name = models.CharField(max_length=100, unique=True)
    suffix = models.CharField(max_length=20, blank=True, default='')
    
    overloadUnitsHasDesignation = models.IntegerField(default=0)
    overloadUnitsNoDesignation = models.IntegerField(default=0) 

    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Academic Attainment"
        verbose_name_plural = "Academic Attainments"
        ordering = ['attainmentId']
