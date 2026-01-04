from django.urls import path
from . import views

urlpatterns = [
    # Rooms
    path('rooms/', views.roomList, name='roomList'),
    path("rooms/live/", views.roomListLive, name="roomListLive"),
    path('rooms/create/', views.roomCreate, name='roomCreate'),
    path('rooms/update/<int:roomId>/', views.roomUpdate, name='roomUpdate'),
    path('rooms/delete/<int:roomId>/', views.roomDelete, name='roomDelete'),

    # GenEd Schedules
    path('genEdSchedules/', views.genedScheduleList, name='genedScheduleList'),
    path("gened-schedules/live/", views.genedScheduleListLive, name="genedScheduleListLive"),
    path('genEdSchedules/create/', views.genedScheduleCreate, name='genedScheduleCreate'),
    path('genEdSchedules/update/<int:scheduleId>/', views.genedScheduleUpdate, name='genedScheduleUpdate'),
    path('genEdSchedules/delete/<int:scheduleId>/', views.genedScheduleDelete, name='genedScheduleDelete'),

    # Semesters
    path('semesters/', views.semesterList, name='semesterList'),
    path("semesters/live/", views.semesterListLive, name="semesterListLive"),
    path('semesters/create/', views.semesterCreate, name='semesterCreate'),
    path('semesters/update/<int:semesterId>/', views.semesterUpdate, name='semesterUpdate'),
    path('semesters/delete/<int:semesterId>/', views.semesterDelete, name='semesterDelete'),

    # Curriculums
    path('curriculums/', views.curriculumList, name='curriculumList'),
    path("curriculums/live/", views.curriculumListLive, name="curriculumListLive"),
    path('curriculums/create/', views.curriculumCreate, name='curriculumCreate'),
    path('curriculums/<int:curriculumId>/update/', views.curriculumUpdate, name='curriculumUpdate'),
    path('curriculums/<int:curriculumId>/delete/', views.curriculumDelete, name='curriculumDelete'),
    path('curriculums/<int:curriculumId>/', views.curriculumDetail, name='curriculumDetail'),

    # Number of Sections per Subject
    path('subject-offerings/', views.subjectOfferingList, name='subjectOfferingList'),
    path('subject-offerings/live/', views.subjectOfferingListLive, name='subjectOfferingListLive'),
    path('subject-offerings/update/<int:offeringId>/', views.subjectOfferingUpdate, name='subjectOfferingUpdate'),
    path("subject-offerings/generate-sections/<int:semesterId>/<int:curriculumId>/", views.generateSections, name="generateSections",),
    path('offerings/<int:offeringId>/sections/config/', views.sectionConfigList, name='sectionConfigList'),

    # Instructor Scheduling Configuration
    path('instructor-scheduling-config/', views.instructorSchedulingConfig, name='instructorSchedulingConfig'),
]
