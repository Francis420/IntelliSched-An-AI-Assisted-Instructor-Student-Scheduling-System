from django.urls import path
from . import views

urlpatterns = [
    path('colleges/', views.collegeList, name='collegeList'),
    path('colleges/create/', views.collegeCreate, name='collegeCreate'),
    path('colleges/<int:collegeId>/update/', views.collegeUpdate, name='collegeUpdate'),
    path('colleges/<int:collegeId>/delete/', views.collegeDelete, name='collegeDelete'),

    path('departments/', views.departmentList, name='departmentList'),
    path('departments/create/', views.departmentCreate, name='departmentCreate'),
    path('departments/<int:departmentId>/update/', views.departmentUpdate, name='departmentUpdate'),
    path('departments/<int:departmentId>/delete/', views.departmentDelete, name='departmentDelete'),

    path('courses/', views.courseList, name='courseList'),
    path('courses/create/', views.courseCreate, name='courseCreate'),
    path('courses/<int:courseId>/update/', views.courseUpdate, name='courseUpdate'),
    path('courses/<int:courseId>/delete/', views.courseDelete, name='courseDelete'),

    path('subjects/', views.subjectList, name='subjectList'),
    path('subjects/create/', views.subjectCreate, name='subjectCreate'),
    path('subjects/<int:subjectId>/update/', views.subjectUpdate, name='subjectUpdate'),
    path('subjects/<int:subjectId>/delete/', views.subjectDelete, name='subjectDelete'),
]
