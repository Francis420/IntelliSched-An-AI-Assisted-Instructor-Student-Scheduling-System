from django.urls import path
from . import views

urlpatterns = [
    # Subject management
    path('subjects/', views.subjectList, name='subjectList'),
    path('subjects/create/', views.subjectCreate, name='subjectCreate'),
    path('subjects/edit/<str:subjectCode>/', views.subjectUpdate, name='subjectUpdate'),
    path('subjects/delete/<str:subjectCode>/', views.subjectDelete, name='subjectDelete'),

    # User management
    path('users/', views.userList, name='userList'),
    path('users/create/', views.userCreate, name='userCreate'),
    path('users/update/<int:userId>/', views.userUpdate, name='userUpdate'),
    path('users/delete/<int:userId>/', views.userDelete, name='userDelete'),
]
