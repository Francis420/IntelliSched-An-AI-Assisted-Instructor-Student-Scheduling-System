from django.urls import path
from . import views

urlpatterns = [
    # Subjects
    path('subjects/', views.subjectList, name='subjectList'),
    path('subjects/live/', views.subjectListLive, name='subjectListLive'),
    path('subjects/create/', views.subjectCreate, name='subjectCreate'),
    path('subjects/edit/<str:subjectCode>/', views.subjectUpdate, name='subjectUpdate'),
    path('subjects/delete/<str:subjectCode>/', views.subjectDelete, name='subjectDelete'),

    # Instructor accounts
    path('instructors/', views.instructorAccountList, name='instructorAccountList'),
    path("instructors/live/", views.instructorAccountListLive, name="instructorAccountListLive"),
    path('instructors/create/', views.instructorAccountCreate, name='instructorAccountCreate'),
    path('instructors/<int:userId>/update/', views.instructorAccountUpdate, name='instructorAccountUpdate'),
    path('instructors/<int:userId>/delete/', views.instructorAccountDelete, name='instructorAccountDelete'),

    # Availability checks
    path('check-username-availability/', views.checkUsernameAvailability, name='check_username_availability'),
    path('check-instructorid-availability/', views.checkInstructorIdAvailability, name='check_instructorid_availability'),
    path('check-studentid-availability/', views.checkStudentIdAvailability, name='check_studentid_availability'),

    # Student accounts
    path('students/', views.studentAccountList, name='studentAccountList'),
    path("students/live/", views.studentAccountListLive, name="studentAccountListLive"),
    path('students/create/', views.studentAccountCreate, name='studentAccountCreate'),
    path('students/update/<int:userId>/', views.studentAccountUpdate, name='studentAccountUpdate'),
]

