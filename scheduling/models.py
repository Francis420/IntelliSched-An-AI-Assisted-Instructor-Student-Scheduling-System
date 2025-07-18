from django.db import models
from core.models import Student, User
from django.utils import timezone


# ---------- Subjects Table ---------- 50 still need dynamic checks for subject code and name
class Subject(models.Model):
    subjectId = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)  # e.g., CS101
    name = models.CharField(max_length=100)
    units = models.IntegerField()
    defaultTerm = models.CharField(max_length=10, choices=[('1st', '1st'), ('2nd', '2nd'), ('Summer', 'Summer')])
    yearLevel = models.CharField(max_length=10, choices=[('1', '1'), ('2', '2'), ('3', '3'), ('4', '4')])
    durationMinutes = models.IntegerField()
    hasLabComponent = models.BooleanField(default=False)
    labDurationMinutes = models.IntegerField(null=True, blank=True)
    preferredDeliveryMode = models.CharField(max_length=10, choices=[('f2f', 'f2f'), ('online', 'online'), ('hybrid', 'hybrid')])
    labDeliveryMode = models.CharField(max_length=10, choices=[('f2f', 'f2f'), ('online', 'online'), ('hybrid', 'hybrid')], null=True, blank=True)
    requiredRoomType = models.CharField(max_length=50, null=True, blank=True)
    requiredLabRoomType = models.CharField(max_length=50, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    isActive = models.BooleanField(default=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


# ---------- Semesters Table ----------
class Semester(models.Model):
    semesterId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=20) 
    academicYear = models.CharField(max_length=20) 
    term = models.CharField(max_length=10, choices=[('1st', '1st'), ('2nd', '2nd'), ('Summer', 'Summer')])
    isActive = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.term} {self.academicYear}"


# ---------- Instructor Matching (AI Result) ----------
class InstructorSubjectMatch(models.Model):
    matchId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    confidenceScore = models.FloatField()
    primaryFactor = models.CharField(max_length=50)  # ENUM in schema
    experienceScore = models.FloatField()
    teachingScore = models.FloatField()
    credentialScore = models.FloatField()
    availabilityScore = models.FloatField()
    notes = models.TextField(null=True, blank=True)
    generatedBy = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generatedAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Match {self.matchId} - {self.instructor.instructorId} -> {self.subject.code}"


# ---------- Subject Offering ----------
class SubjectOffering(models.Model):
    offerId = models.AutoField(primary_key=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    match = models.ForeignKey(InstructorSubjectMatch, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    sectionCode = models.CharField(max_length=10)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject.code} - {self.sectionCode}"


# ---------- Section Table ---------- 50 check notes
class Section(models.Model):
    sectionId = models.AutoField(primary_key=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    sectionCode = models.CharField(max_length=10)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject.code} - Section {self.sectionCode}"


# ---------- Room Table ---------- 50 check notes for info
class Room(models.Model):
    roomId = models.AutoField(primary_key=True)
    roomCode = models.CharField(max_length=20)
    building = models.CharField(max_length=100)
    capacity = models.IntegerField()
    type = models.CharField(max_length=50)
    isActive = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.roomCode} - {self.building}"


# ---------- Schedule Table ----------
class Schedule(models.Model):
    scheduleId = models.AutoField(primary_key=True)
    offer = models.ForeignKey(SubjectOffering, on_delete=models.CASCADE)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    dayOfWeek = models.CharField(max_length=10, choices=[
        ('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'), ('Friday', 'Friday'), ('Saturday', 'Saturday')
    ])
    startTime = models.TimeField()
    endTime = models.TimeField()
    scheduleType = models.CharField(max_length=10, choices=[('lecture', 'Lecture'), ('lab', 'Lab')])
    isOvertime = models.BooleanField(default=False)
    scheduleStatus = models.CharField(max_length=20, choices=[('draft', 'Draft'), ('final', 'Final'), ('archived', 'Archived')])
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.offer.subject.code} - {self.dayOfWeek} ({self.startTime}-{self.endTime})"


# ---------- Schedule Control ----------
class ScheduleControl(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    updatedBy = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=30, choices=[('generating', 'Generating'), ('pendingApproval', 'Pending Approval'), ('finalized', 'Finalized')])
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Schedule {self.schedule.scheduleId} - {self.status}"


# ---------- Enrollment ----------
class Enrollment(models.Model):
    enrollmentId = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'subject', 'section')

    def __str__(self):
        return f"{self.student.studentId} enrolled in {self.subject.code}"


# ---------- GenEdSchedules ---------- 50 check notes
class GenEdSchedule(models.Model):
    genedScheduleId = models.AutoField(primary_key=True)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, null=True, blank=True)
    code = models.CharField(max_length=20)
    subjectName = models.CharField(max_length=100)
    sectionCode = models.CharField(max_length=10)
    instructorName = models.CharField(max_length=100, null=True, blank=True)
    dayOfWeek = models.CharField(max_length=10)
    startTime = models.TimeField()
    endTime = models.TimeField()
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"GenEd {self.code} - {self.sectionCode}"


# ---------- InstructorSubjectMatchHistory ----------
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
