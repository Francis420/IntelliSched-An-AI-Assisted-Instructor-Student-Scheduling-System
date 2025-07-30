from django.urls import path
from . import views

urlpatterns = [
    path('students/create/', views.studentAccountCreate, name='studentAccountCreate'),

    # Student Enrollments
    path('enrollments/',views.enrollmentList, name='enrollmentList'),
    path("enrollments/live/", views.enrollmentListLive, name="enrollmentListLive"),
    path('enrollments/create/', views.enrollmentCreate, name='enrollmentCreate'),
    path('enrollments/update/<int:enrollmentId>/', views.enrollmentUpdate, name='enrollmentUpdate'),
    path('enrollments/delete/<int:enrollmentId>/', views.enrollmentDelete, name='enrollmentDelete'),
]