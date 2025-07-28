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
    matchScore = models.FloatField()
    matchLevel = models.IntegerField()
    experienceScore = models.FloatField()
    teachingScore = models.FloatField()
    credentialScore = models.FloatField()
    availabilityScore = models.FloatField()
    primaryFactor = models.CharField(max_length=50)
    notes = models.TextField(null=True, blank=True)
    explanation = models.TextField(null=True, blank=True)
    previousMatchScore = models.FloatField(null=True, blank=True)
    scoreChange = models.FloatField(null=True, blank=True)
    matchReason = models.CharField(max_length=100, null=True, blank=True)
    isRecommended = models.BooleanField(default=True)
    batchId = models.CharField(max_length=100)
    isLatest = models.BooleanField(default=True)
    modelVersion = models.CharField(max_length=50, null=True, blank=True)
    generatedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Match {self.matchId} - {self.instructor.instructorId} -> {self.subject.code}"
    
    class Meta:
        ordering = ['-generatedAt']


# ---------- InstructorSubjectMatchHistory ----------
# This model stores the history of instructor-subject matches, including confidence scores and other metrics.
# It allows tracking changes over time and provides insights into the matching process.
class InstructorSubjectMatchHistory(models.Model):
    matchId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    confidenceScore = models.FloatField()
    previousMatchScore = models.FloatField(null=True, blank=True)
    scoreChange = models.FloatField(null=True, blank=True)  # current - previous
    primaryFactor = models.CharField(max_length=50)
    experienceScore = models.FloatField()
    teachingScore = models.FloatField()
    credentialScore = models.FloatField()
    availabilityScore = models.FloatField()
    explanation = models.TextField(null=True, blank=True)  # NEW: Add explanation for that run
    modelVersion = models.CharField(max_length=50, null=True, blank=True)  # NEW: version of embedding/model used
    batchId = models.CharField(max_length=100)  # Run grouping ID (e.g., UUID)
    generatedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[History] {self.instructor.instructorId} - {self.subject.code} @ {self.generatedAt.strftime('%Y-%m-%d %H:%M')}"

