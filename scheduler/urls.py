# scheduler/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('output/', views.scheduleOutput, name='scheduleOutput'),
    path("mySchedule/", views.instructorScheduleView, name="instructorScheduleView"),
    path("dashboard/", views.scheduler_dashboard, name="schedulerDashboard"),
    path("start/", views.start_scheduler, name="startScheduler"),
    path("stop/", views.stop_scheduler, name="stopScheduler"),
    path("status/", views.scheduler_status, name="schedulerStatus"),

]
