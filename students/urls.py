from django.urls import path
from . import views

urlpatterns = [
    path('students/create/', views.studentAccountCreate, name='studentAccountCreate'),
]