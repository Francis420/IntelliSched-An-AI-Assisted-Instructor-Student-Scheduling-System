from rest_framework import serializers
from django.contrib.auth import authenticate
from core.models import User

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['username'], password=data['password'])
        if user and user.isActive:
            data['user'] = user
            return data
        raise serializers.ValidationError("Invalid credentials or inactive account")
