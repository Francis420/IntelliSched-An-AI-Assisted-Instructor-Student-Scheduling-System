from django.db import models
from core.models import User
from scheduling.models import Subject

# ---------- Instructor Matching (AI Result) ----------
# This model stores the results of AI-based instructor matching for subjects, including confidence scores and other metrics.
# It links instructors to subjects based on various factors like experience, teaching ability, and availability.
class InstructorSubjectMatch(models.Model):
    matchId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    score = models.FloatField(default=0.0)
    primaryFactor = models.CharField(max_length=50) 
    experienceScore = models.FloatField()
    teachingScore = models.FloatField()
    credentialScore = models.FloatField()
    availabilityScore = models.FloatField()
    notes = models.TextField(null=True, blank=True)
    generatedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Match {self.matchId} - {self.instructor.instructorId} -> {self.subject.code}"
    
    class Meta:
        unique_together = ('instructor', 'subject')
        ordering = ['-score']

# ---------- InstructorSubjectMatchHistory ----------
# This model stores the history of instructor-subject matches, including confidence scores and other metrics.
# It allows tracking changes over time and provides insights into the matching process.
class InstructorSubjectMatchHistory(models.Model):
    matchId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    confidenceScore = models.FloatField()
    primaryFactor = models.CharField(max_length=50)
    experienceScore = models.FloatField()
    teachingScore = models.FloatField()
    credentialScore = models.FloatField()
    availabilityScore = models.FloatField()
    notes = models.TextField(blank=True, null=True)
    generatedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[History] {self.instructor.instructorId} - {self.subject.code}"
