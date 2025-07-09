from django.contrib import admin
from .models import Subject, SubjectOffering, InstructorMatching, Room, Schedule

admin.site.register(Subject)
admin.site.register(SubjectOffering)
admin.site.register(InstructorMatching)
admin.site.register(Room)
admin.site.register(Schedule)
