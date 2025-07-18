from django.urls import path
from . import views

urlpatterns = [
    # Subjects
    path('subjects/', views.subjectList, name='subjectList'),
    path('subjects/create/', views.subjectCreate, name='subjectCreate'),
    path('subjects/edit/<str:subjectCode>/', views.subjectUpdate, name='subjectUpdate'),
    path('subjects/delete/<str:subjectCode>/', views.subjectDelete, name='subjectDelete'),

    # Instructor accounts
    path('instructors/', views.instructorAccountList, name='instructorAccountList'),
    path('instructors/create/', views.instructorAccountCreate, name='instructorAccountCreate'),
    path('instructors/<int:userId>/update/', views.instructorAccountUpdate, name='instructorAccountUpdate'),
    path('instructors/<int:userId>/delete/', views.instructorAccountDelete, name='instructorAccountDelete'),

    # Check if username/instructorId exists
    path('check-username-availability/', views.checkUsernameAvailability, name='checkUsernameAvailability'),
    path('check-instructor-id-availability/', views.checkInstructorIdAvailability, name='checkInstructorIdAvailability'),

    # Student accounts
    path('students/', views.studentAccountList, name='studentAccountList'),
    path('students/create/', views.studentAccountCreate, name='studentAccountCreate'),
    path('students/update/<int:userId>/', views.studentAccountUpdate, name='studentAccountUpdate'),
]
