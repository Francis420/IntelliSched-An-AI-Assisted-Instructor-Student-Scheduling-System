from django.db import models
from instructors.models import Instructor
from core.models import User
from django.utils import timezone
from core.models import Course


# ---------- Subject ----------
class Subject(models.Model):
    SEMESTER_CHOICES = [('1st', '1st'), ('2nd', '2nd'), ('Summer', 'Summer')]

    subjectId = models.AutoField(primary_key=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    subjectCode = models.CharField(max_length=20, unique=True)
    subjectName = models.CharField(max_length=100)
    units = models.IntegerField()
    yearLevel = models.IntegerField()
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    isActive = models.BooleanField(default=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    lastUpdated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.subjectCode} - {self.subjectName}"


# ---------- Instructor Matching (AI Results) ----------
class InstructorMatching(models.Model):
    matchId = models.AutoField(primary_key=True)
    experienceId = models.IntegerField(blank=True, null=True)
    teachingId = models.IntegerField(blank=True, null=True)
    availabilityId = models.IntegerField(blank=True, null=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    confidence = models.FloatField()
    notes = models.TextField(blank=True, null=True)
    generatedBy = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    createdAt = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Match #{self.matchId} – {self.subject.subjectCode}"


# ---------- Subject Offering ----------
class SubjectOffering(models.Model):
    offeringId = models.AutoField(primary_key=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    match = models.ForeignKey(InstructorMatching, on_delete=models.CASCADE)
    sectionCode = models.CharField(max_length=5)
    createdAt = models.DateTimeField(default=timezone.now)
    lastUpdated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.subject.subjectCode} - Sec {self.sectionCode}"


# ---------- Room ----------
class Room(models.Model):
    roomId = models.AutoField(primary_key=True)
    roomCode = models.CharField(max_length=20, unique=True)
    building = models.CharField(max_length=100)
    capacity = models.IntegerField()
    type = models.CharField(max_length=50)
    isActive = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    createdAt = models.DateTimeField(default=timezone.now)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.roomCode} - {self.building}"


# ---------- Final Schedule ----------
class Schedule(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('final', 'Final'), ('archived', 'Archived')]
    DAY_CHOICES = [
        ('Mon', 'Monday'), ('Tue', 'Tuesday'), ('Wed', 'Wednesday'),
        ('Thu', 'Thursday'), ('Fri', 'Friday'), ('Sat', 'Saturday')
    ]

    scheduleId = models.AutoField(primary_key=True)
    offering = models.ForeignKey(SubjectOffering, on_delete=models.CASCADE)
    instructor = models.ForeignKey(Instructor, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    dayOfWeek = models.CharField(max_length=10, choices=DAY_CHOICES)
    startTime = models.TimeField()
    endTime = models.TimeField()
    semester = models.CharField(max_length=50)  # e.g., "1st Sem AY 2025–2026"
    scheduleStatus = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    createdAt = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.offering.subject.subjectCode} {self.dayOfWeek} {self.startTime}-{self.endTime}"
