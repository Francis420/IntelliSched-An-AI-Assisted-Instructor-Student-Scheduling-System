from django.db import models
from core.models import Student, User
from django.utils import timezone


# ---------- Curriculum Table ----------
# This model represents the curriculum to avoid conflicts of new and old curriculums, including its name, effective school year,
class Curriculum(models.Model):
    curriculumId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)  # e.g., "2021 Curriculum"
    effectiveSy = models.CharField(max_length=20)  # e.g., "S.Y. 2021-2022"
    description = models.TextField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name



# ---------- Subjects Table ---------- 60 still need dynamic checks for subject code and name
# This model represents subjects offered by the IT department, including their code, name, units, and other attributes.
class Subject(models.Model):
    subjectId = models.AutoField(primary_key=True)
    curriculum = models.ForeignKey("Curriculum", on_delete=models.CASCADE, related_name="subjects")

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    units = models.IntegerField()
    durationMinutes = models.IntegerField()
    defaultTerm = models.IntegerField(choices=[(0, '1st'), (1, '2nd'), (2, 'Midyear')])
    yearLevel = models.IntegerField(choices=[(1, '1st'), (2, '2nd'), (3, '3rd'), (4, '4th')])
    hasLab = models.BooleanField(default=False)
    labDurationMinutes = models.IntegerField(null=True, blank=True)
    isPriorityForRooms = models.BooleanField(default=False)
    isActive = models.BooleanField(default=True)
    subjectTopics = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    @property
    def normalizedUnits(self):
        return self.units / 3

    @property
    def normalizedDuration(self):
        return self.durationMinutes / 180

    @property
    def safeLabDuration(self):
        return self.labDurationMinutes if self.hasLab else 0

    def __str__(self):
        return f"[{self.curriculum.name}] {self.code} - {self.name}"



# ---------- Semester Table ----------
# This model represents semesters in the academic calendar, including their name, academic year, and term
class Semester(models.Model):
    semesterId = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    academicYear = models.CharField(max_length=20) 
    term = models.CharField(max_length=10, choices=[('1st', '1st'), ('2nd', '2nd'), ('Midyear', 'Midyear')])
    isActive = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}"


# ---------- Instructor Matching (AI Result) ----------
# This model stores the results of AI-based instructor matching for subjects, including confidence scores and other metrics.
# It links instructors to subjects based on various factors like experience, teaching ability, and availability.
class InstructorSubjectMatch(models.Model):
    matchId = models.AutoField(primary_key=True)
    instructor = models.ForeignKey('core.Instructor', on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    confidenceScore = models.FloatField()
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


# ---------- Subject Offering Table ----------
# This model represents the offering of a subject in a specific semester, including the section code and associated instructor match.
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
# This model represents sections of subjects in a specific semester, linking to the subject and semester models.
class Section(models.Model):
    sectionId = models.AutoField(primary_key=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    sectionCode = models.CharField(max_length=10)
    createdAt = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject.code} - Section {self.sectionCode}"


# ---------- Room Table ---------- 50 check notes for info
# This model represents rooms available for scheduling classes, including their code, building, capacity, and type.
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
# This model represents the schedule of classes, linking subject offerings, instructors, sections, rooms, and semesters.
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
# This model tracks the control and status of schedules, including who updated it and its current status.
class ScheduleControl(models.Model):
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    updatedBy = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=30, choices=[('generating', 'Generating'), ('pendingApproval', 'Pending Approval'), ('finalized', 'Finalized')])
    updatedAt = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Schedule {self.schedule.scheduleId} - {self.status}"


# ---------- Enrollment ---------- # scheduleId may cause errors, rebuild the database if it does.
# This model represents student enrollments in schedules, linking students to specific schedules.
class Enrollment(models.Model):
    enrollmentId = models.AutoField(primary_key=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE)
    enrollmentDate = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.studentId} enrolled in {self.schedule.offer.subject.code} - {self.schedule.section.sectionCode}"



# ---------- GenEdSchedules ---------- 50 check notes
# This model represents the General Education schedules, linking them to semesters and including details like code, subject name, section code, instructor name, and time.
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
