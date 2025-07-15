from django.contrib import admin
from .models import InstructorSubjectPreference, InstructorExperience, TeachingHistory, InstructorAvailability, InstructorCredentials

admin.site.register(InstructorSubjectPreference)
admin.site.register(InstructorCredentials)
admin.site.register(InstructorExperience)
admin.site.register(TeachingHistory)
admin.site.register(InstructorAvailability)
