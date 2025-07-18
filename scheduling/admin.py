from django.contrib import admin
from .models import (
    Subject, 
    Semester, 
    InstructorSubjectMatch, 
    SubjectOffering, 
    Section, 
    Room, 
    Schedule, 
    ScheduleControl, 
    Enrollment, 
    GenEdSchedule,  
    InstructorSubjectMatchHistory
    )



admin.site.register(Subject)
admin.site.register(Semester)
admin.site.register(InstructorSubjectMatch)
admin.site.register(SubjectOffering)
admin.site.register(Section)
admin.site.register(Room)
admin.site.register(Schedule)
admin.site.register(ScheduleControl)
admin.site.register(Enrollment)
admin.site.register(GenEdSchedule)
admin.site.register(InstructorSubjectMatchHistory)




