from django.urls import path
from . import views

urlpatterns = [
    # Rooms
    path('rooms/', views.roomList, name='roomList'),
    path('rooms/create/', views.roomCreate, name='roomCreate'),
    path('rooms/update/<int:roomId>/', views.roomUpdate, name='roomUpdate'),
    path('rooms/delete/<int:roomId>/', views.roomDelete, name='roomDelete'),

    # GenEd Schedules
    path('genEdSchedules/', views.genedScheduleList, name='genedScheduleList'),
    path('genEdSchedules/create/', views.genedScheduleCreate, name='genedScheduleCreate'),
    path('genEdSchedules/update/<int:scheduleId>/', views.genedScheduleUpdate, name='genedScheduleUpdate'),
    path('genEdSchedules/delete/<int:scheduleId>/', views.genedScheduleDelete, name='genedScheduleDelete'),

    # Student Enrollments
    path('enrollments/',views.enrollmentList, name='enrollmentList'),
    path('enrollments/create/', views.enrollmentCreate, name='enrollmentCreate'),
    path('enrollments/update/<int:enrollmentId>/', views.enrollmentUpdate, name='enrollmentUpdate'),
    path('enrollments/delete/<int:enrollmentId>/', views.enrollmentDelete, name='enrollmentDelete'),

    # Semesters
    path('semesters/', views.semesterList, name='semesterList'),
    path('semesters/create/', views.semesterCreate, name='semesterCreate'),
    path('semesters/update/<int:semesterId>/', views.semesterUpdate, name='semesterUpdate'),
    path('semesters/delete/<int:semesterId>/', views.semesterDelete, name='semesterDelete'),

    # Curriculums
    path('curriculums/', views.curriculumList, name='curriculumList'),
    path('curriculums/create/', views.curriculumCreate, name='curriculumCreate'),
    path('curriculums/<int:curriculumId>/update/', views.curriculumUpdate, name='curriculumUpdate'),
    path('curriculums/<int:curriculumId>/delete/', views.curriculumDelete, name='curriculumDelete'),
    path('curriculums/<int:curriculumId>/', views.curriculumDetail, name='curriculumDetail'),# Check subs under that curiculum
]
