from django.contrib import admin
from .models import (
    Subject, 
    Semester, 
    Section, 
    Room, 
    Schedule, 
    ScheduleControl, 
    GenEdSchedule,  
    Curriculum,
    )



admin.site.register(Subject)
admin.site.register(Semester)
admin.site.register(Section)
admin.site.register(Room)
admin.site.register(Schedule)
admin.site.register(ScheduleControl)
admin.site.register(GenEdSchedule)
@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = ("name", "effectiveSy", "isActive", "createdAt")
    list_filter = ("isActive", "effectiveSy")
    search_fields = ("name", "effectiveSy")





