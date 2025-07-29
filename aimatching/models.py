from django.db import models
from core.models import User
from scheduling.models import Subject


class InstructorSubjectMatch(models.Model):
    matchId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    subject = models.ForeignKey('scheduling.Subject', on_delete=models.CASCADE)
    latestHistory = models.OneToOneField(
        'InstructorSubjectMatchHistory',
        on_delete=models.CASCADE,
        related_name='current_match',
        null=True, blank=True
    )
    isRecommended = models.BooleanField(default=True)
    isLatest = models.BooleanField(default=True)
    batchId = models.CharField(max_length=100)
    modelVersion = models.CharField(max_length=50, null=True, blank=True)
    generatedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Latest Match {self.instructor.instructorId} -> {self.subject.code}"

    class Meta:
        ordering = ['-generatedAt']


class InstructorSubjectMatchHistory(models.Model):
    historyId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    subject = models.ForeignKey('scheduling.Subject', on_delete=models.CASCADE)
    confidenceScore = models.FloatField()
    experienceScore = models.FloatField()
    teachingScore = models.FloatField()
    credentialScore = models.FloatField()
    preferenceScore = models.FloatField(default=0.0)
    primaryFactor = models.CharField(max_length=50)
    previousMatchScore = models.FloatField(null=True, blank=True)
    scoreChange = models.FloatField(null=True, blank=True)
    explanation = models.TextField(null=True, blank=True)
    modelVersion = models.CharField(max_length=50, null=True, blank=True)
    batchId = models.CharField(max_length=100)
    generatedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[History] {self.instructor.instructorId} - {self.subject.code} (Rank {self.rank})"
    

class MatchingConfig(models.Model):
    configId = models.AutoField(primary_key=True)
    semester = models.OneToOneField('scheduling.Semester', on_delete=models.CASCADE)
    teachingWeight = models.FloatField(default=0.2)
    credentialsWeight = models.FloatField(default=0.3)
    experienceWeight = models.FloatField(default=0.3)
    preferenceWeight = models.FloatField(default=0.2)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"MatchingConfig for {self.semester.name}"

    

class MatchingRun(models.Model):
    runId = models.AutoField(primary_key=True)
    semester = models.ForeignKey('scheduling.Semester', on_delete=models.CASCADE)
    batchId = models.CharField(max_length=100, unique=True)
    totalSubjects = models.IntegerField()
    totalInstructors = models.IntegerField()
    generatedBy = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Run {self.batchId} ({self.semester.name})"

    def get_results(self):
        return InstructorSubjectMatch.objects.filter(batchId=self.batchId).select_related(
            "instructor", "subject", "latestHistory"
        ).order_by("subject__code", "latestHistory__rank")
    
class MatchingProgress(models.Model):
    batchId = models.CharField(max_length=100, primary_key=True)
    semester = models.ForeignKey('scheduling.Semester', on_delete=models.CASCADE)
    totalTasks = models.IntegerField(default=0)
    completedTasks = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="running")  # running, completed, failed
    generated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    startedAt = models.DateTimeField(auto_now_add=True)
    finishedAt = models.DateTimeField(null=True, blank=True)

    def progress_percent(self):
        return (self.completedTasks / self.totalTasks) * 100 if self.totalTasks else 0

