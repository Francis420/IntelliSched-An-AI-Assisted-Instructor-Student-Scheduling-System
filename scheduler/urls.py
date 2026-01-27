# scheduler/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('scheduleOutput/', views.scheduleOutput, name='scheduleOutput'),
    path('finalize/<int:semester_id>/', views.finalizeSchedule, name='finalizeSchedule'),
    path('finalize/<str:semester_id>/revert/', views.revertFinalizedSchedule, name='revertFinalizedSchedule'),
    path('revertSchedule/', views.revertSchedule, name='revertSchedule'),
    path("mySchedule/", views.instructorScheduleView, name="instructorScheduleView"),
    path("schedulerDashboard/", views.schedulerDashboard, name="schedulerDashboard"),
    path("start/", views.startScheduler, name="startScheduler"),
    path("stop/", views.stopScheduler, name="stopScheduler"),
    path("status/", views.schedulerStatus, name="schedulerStatus"),

    # Instructor Workload Export(excel and preview)
    path('instructor/workload/preview/', views.previewWorkload, name='previewWorkload'),
    path('instructor/workload/exportInstructorWorkload/', views.exportWorkloadExcel, name='exportWorkloadExcel'),

    #For Minor Revisions on Finalized Schedules
    path('sectionBlockManager/', views.sectionBlockScheduler, name='sectionBlockScheduler'),
    path('api/getInstructorConflicts/', views.getInstructorConflicts, name='getInstructorConflicts'),
    path('api/updateScheduleSlot/', views.updateScheduleSlot, name='updateScheduleSlot'),
    path('roomManager/', views.roomScheduler, name='roomScheduler'),
    path('instructorLoadManager/', views.instructorLoad, name='instructorLoad'),
    path('api/getInstructorLoadStats/', views.getInstructorLoadStats, name='getInstructorLoadStats'),

    path('print/roomSchedule/<int:roomId>/<int:semesterId>/', views.previewRoomSchedule, name='previewRoomSchedule'),
    path('print/sectionSchedule/<str:blockStr>/<int:semesterId>/', views.previewSectionBlockSchedule, name='previewSectionBlockSchedule'),
]
