from django.urls import path
from . import views

urlpatterns = [
    # Rooms
    path('rooms/', views.roomList, name='roomList'),
    path('rooms/create/', views.roomCreate, name='roomCreate'),
    path('rooms/update/<int:roomId>/', views.roomUpdate, name='roomUpdate'),
    path('rooms/delete/<int:roomId>/', views.roomDelete, name='roomDelete'),
]
