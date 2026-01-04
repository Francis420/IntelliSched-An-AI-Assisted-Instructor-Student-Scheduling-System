from django.contrib import admin
from django.urls import path, include
from core.views import home
from django.conf import settings
from django.conf.urls.static import static

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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
