# scheduler/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('scheduleOutput/', views.scheduleOutput, name='scheduleOutput'),
    path('finalize/<int:semester_id>/', views.finalizeSchedule, name='finalizeSchedule'),
    path('finalize/<str:semester_id>/revert/', views.revertFinalizedSchedule, name='revertFinalizedSchedule'),
    path('revertSchedule/', views.revertSchedule, name='revertSchedule'),
    path("mySchedule/", views.instructorScheduleView, name="instructorScheduleView"),
    path("dashboard/", views.scheduler_dashboard, name="schedulerDashboard"),
    path("start/", views.start_scheduler, name="startScheduler"),
    path("stop/", views.stop_scheduler, name="stopScheduler"),
    path("status/", views.scheduler_status, name="schedulerStatus"),
    path("roomUtilization/", views.roomUtilization, name="roomUtilization"),
    path('instructor/workload/preview/', views.previewWorkload, name='previewWorkload'),
    path('instructor/workload/exportInstructorWorkload/', views.exportWorkloadExcel, name='exportWorkloadExcel'),
]
