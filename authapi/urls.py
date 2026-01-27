# authapi\urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.loginView, name='login'),
    path('logout/', views.logoutView, name='logout'),

    path('department/dashboard/', views.deptHeadDashboard, name='deptHeadDashboard'),
    path('instructor/dashboard/', views.instructorDashboard, name='instructorDashboard'),
]
