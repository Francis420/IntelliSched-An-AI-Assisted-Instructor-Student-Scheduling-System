# aimatching/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.matchingDashboard, name="matchingDashboard"),

    path('configs/', views.configList, name="configList"),
    path('configs/<int:semesterId>/update/', views.configUpdate, name="configUpdate"),

    path('matching/start/', views.matchingStart, name="matchingStart"), 
    path('matching/run/', views.matchingRun, name="matchingRun"),
    path('matching/progress/<uuid:batchId>/', views.matchingProgressPage, name='matchingProgressPage'),
    path('matching/progress/data/<uuid:batchId>/', views.matchingProgress, name='matchingProgress'),
    path('matching/results/<str:batchId>/', views.matchingResults, name="matchingResults"),
    path('matching/results/<str:batchId>/live/',views.matchingResultsLive, name='matchingResultsLive'),
]
