from django.contrib import admin
from django.urls import path, include
from core.views import home

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('auth/', include('authapi.urls')),
    path('core/', include('core.urls')),
    path('students/', include('students.urls')),
    path('instructors/', include('instructors.urls')),
    path('scheduling/', include('scheduling.urls')),
    path('aimatching/', include('aimatching.urls')),
    path('scheduler/', include('scheduler.urls')),
]
