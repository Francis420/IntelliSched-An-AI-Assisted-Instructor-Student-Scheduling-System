from django.contrib import admin
from .models import User, College, Department, UserLogin

admin.site.register(User)
admin.site.register(College)
admin.site.register(Department)
admin.site.register(UserLogin)
