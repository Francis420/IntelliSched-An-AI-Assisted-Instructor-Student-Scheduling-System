# core\urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('auditlogs/', views.auditlog_view, name='auditlogView'),

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

    # Recommendation Dashboard
    path('recommendations/', views.recommendInstructors, name='recommendations'),

    # Instructor Profile
    path('profile/', views.instructorProfile, name='instructorProfile'),

    # Department Head Management
    path('manageDeptHead/', views.manageDeptHead, name='manageDeptHead'),

    # User Manual
    path('userManual/', views.userManual, name='userManual'),

    # IntelliSched Documentation
    path('intellischedDocumentation/', views.intellischedDocumentation, name='intellischedDocumentation'),

    # IntelliSched About
    path('intellischedAbout/', views.intellischedAbout, name='intellischedAbout'),
]

