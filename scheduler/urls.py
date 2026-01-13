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

    # Instructor Workload Export(excel and preview)
    path('instructor/workload/preview/', views.previewWorkload, name='previewWorkload'),
    path('instructor/workload/exportInstructorWorkload/', views.exportWorkloadExcel, name='exportWorkloadExcel'),

    #For Minor Revisions on Finalized Schedules
    path('sectionBlockManager/', views.sectionBlockScheduler, name='sectionBlockScheduler'),
    path('api/getInstructorConflicts/', views.getInstructorConflicts, name='getInstructorConflicts'),
    path('api/updateScheduleSlot/', views.updateScheduleSlot, name='updateScheduleSlot'),
    path('roomManager/', views.roomScheduler, name='roomScheduler'),
    path('instructorLoadManager/', views.instructorLoad, name='instructorLoad'),

    path('rooms/export/<int:room_id>/', views.exportRoomSchedule, name='exportRoomSchedule'),
    path('api/getInstructorLoadStats/', views.getInstructorLoadStats, name='getInstructorLoadStats'),
]
