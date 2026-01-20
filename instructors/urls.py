from django.urls import path
from . import views

urlpatterns = [
    # Instructor Dashboard
    path('instructorPortfolio/', views.instructorPortfolio, name='instructorPortfolio'),

    # Instructor Experience
    path('experiences/', views.experienceList, name='experienceList'),
    path('experiences/live/', views.experienceListLive, name="experienceListLive"),
    path('experiences/create/', views.experienceCreate, name='experienceCreate'),
    path('experiences/<int:experienceId>/edit/', views.experienceUpdate, name='experienceUpdate'),
    path('experiences/<int:experienceId>/delete/', views.experienceDelete, name='experienceDelete'),

    # Instructor Credentials
    path('credentials/', views.credentialList, name='credentialList'),
    path("credentials/live/", views.credentialListLive, name="credentialListLive"),
    path('credentials/create/', views.credentialCreate, name='credentialCreate'),
    path('credentials/<int:credentialId>/update/', views.credentialUpdate, name='credentialUpdate'),
    path('credentials/<int:credentialId>/delete/', views.credentialDelete, name='credentialDelete'),

    # Teaching History / Legacy Experience
    path('legacyExperience/', views.legacyExperienceList, name='legacyExperienceList'),
    path('legacyExperience/live/', views.legacyExperienceListLive, name='legacyExperienceListLive'),
    path('legacyExperience/create/', views.legacyExperienceCreate, name='legacyExperienceCreate'),
    path('legacyExperience/<int:experienceId>/update/', views.legacyExperienceUpdate, name='legacyExperienceUpdate'),
    path('legacyExperience/<int:experienceId>/delete/', views.legacyExperienceDelete, name='legacyExperienceDelete'),

    # Instructor Ranks
    path('ranks/', views.instructorRankList, name='instructorRankList'),
    path('ranks/create/', views.instructorRankCreate, name='instructorRankCreate'),
    path('ranks/<int:rankId>/update/', views.instructorRankUpdate, name='instructorRankUpdate'),

    # Instructor Designations
    path('designations/', views.instructorDesignationList, name='instructorDesignationList'),
    path('designations/create/', views.instructorDesignationCreate, name='instructorDesignationCreate'),
    path('designations/<int:designationId>/update/', views.instructorDesignationUpdate, name='instructorDesignationUpdate'),

    # Instructor Academic Attainments
    path('attainments/', views.instructorAttainmentList, name='instructorAttainmentList'),
    path('attainments/create/', views.instructorAttainmentCreate, name='instructorAttainmentCreate'),
    path('attainments/<int:attainmentId>/update/', views.instructorAttainmentUpdate, name='instructorAttainmentUpdate'),
]
