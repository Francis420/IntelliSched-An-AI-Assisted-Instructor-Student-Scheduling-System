from django.urls import path
from . import views

urlpatterns = [
    # Instructor Experience
    path('experiences/', views.experienceList, name='experienceList'),
    path('experiences/live/', views.experienceListLive, name="experienceListLive"),
    path('experiences/create/', views.experienceCreate, name='experienceCreate'),
    path('experiences/<int:experienceId>/edit/', views.experienceUpdate, name='experienceUpdate'),
    path('experiences/<int:experienceId>/delete/', views.experienceDelete, name='experienceDelete'),
    
    # Instructor Availability
    path('availability/', views.availabilityList, name='availabilityList'),
    path("availability/live/", views.availabilityListLive, name="availabilityListLive"),
    path('availability/create/', views.availabilityCreate, name='availabilityCreate'),
    path('availability/<int:availabilityId>/edit/', views.availabilityUpdate, name='availabilityUpdate'),
    path('availability/<int:availabilityId>/delete/', views.availabilityDelete, name='availabilityDelete'),

    # Instructor Credentials
    path('credentials/', views.credentialList, name='credentialList'),
    path("credentials/live/", views.credentialListLive, name="credentialListLive"),
    path('credentials/create/', views.credentialCreate, name='credentialCreate'),
    path('credentials/<int:credentialId>/update/', views.credentialUpdate, name='credentialUpdate'),
    path('credentials/<int:credentialId>/delete/', views.credentialDelete, name='credentialDelete'),

    # Instructor Preferences
    path('preferences/', views.preferenceList, name='preferenceList'),
    path("preferences/live/", views.preferenceListLive, name="preferenceListLive"),
    path('preferences/create/', views.preferenceCreate, name='preferenceCreate'),
    path('preferences/<int:preferenceId>/update/', views.preferenceUpdate, name='preferenceUpdate'),
    path('preferences/<int:preferenceId>/delete/', views.preferenceDelete, name='preferenceDelete'),

    # Teaching History
    path('teachingHistory/', views.teachingHistoryList, name='teachingHistoryList'),
    path("teachingHistory/live/", views.teachingHistoryListLive, name="teachingHistoryListLive"),
    path('teachingHistory/create/', views.teachingHistoryCreate, name='teachingHistoryCreate'),
    path('teachingHistory/<int:teachingId>/update/', views.teachingHistoryUpdate, name='teachingHistoryUpdate'),
    path('teachingHistory/<int:teachingId>/delete/', views.teachingHistoryDelete, name='teachingHistoryDelete'),
]
