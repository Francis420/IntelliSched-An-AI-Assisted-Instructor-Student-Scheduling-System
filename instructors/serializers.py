from rest_framework import serializers
from .models import InstructorExperience

class InstructorExperienceSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstructorExperience
        fields = '__all__'
