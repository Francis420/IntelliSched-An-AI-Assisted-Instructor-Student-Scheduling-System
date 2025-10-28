# scheduler/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('output/', views.scheduleOutput, name='scheduleOutput'),
    path("mySchedule/", views.instructorScheduleView, name="instructorScheduleView"),
]
