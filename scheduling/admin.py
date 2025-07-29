from django.contrib import admin
from .models import (
    Subject, 
    Semester, 
    Section, 
    Room, 
    Schedule, 
    ScheduleControl, 
    Enrollment, 
    GenEdSchedule,  
    )



admin.site.register(Subject)
admin.site.register(Semester)
admin.site.register(Section)
admin.site.register(Room)
admin.site.register(Schedule)
admin.site.register(ScheduleControl)
admin.site.register(Enrollment)
admin.site.register(GenEdSchedule)




