from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.loginView, name='login'),
    path('logout/', views.logoutView, name='logout'),

    # Test Dashboards
    path('adminpanel/dashboard/', views.sysAdminDashboard, name='sysAdminDashboard'),
    path('department/dashboard/', views.deptHeadDashboard, name='deptheadDashboard'),
    path('instructor/dashboard/', views.instructorDashboard, name='instructorDashboard'),
    path('student/dashboard/', views.studentDashboard, name='studentDashboard'),
]
