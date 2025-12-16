from django.contrib import admin
from .models import User, Role, UserLogin, Instructor

admin.site.register(User)
admin.site.register(UserLogin)
admin.site.register(Role)
admin.site.register(Instructor)
