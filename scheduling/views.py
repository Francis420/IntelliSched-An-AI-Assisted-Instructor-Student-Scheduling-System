from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from authapi.views import has_role  
from scheduling.models import Room
from django.db import transaction


# ---------- Rooms ----------
@login_required
@has_role('deptHead')
def roomList(request):
    rooms = Room.objects.all().order_by('roomCode')
    return render(request, 'scheduling/rooms/list.html', {'rooms': rooms})


@login_required
@has_role('deptHead')
@transaction.atomic
def roomCreate(request):
    if request.method == 'POST':
        roomCode = request.POST.get('roomCode')
        building = request.POST.get('building')
        capacity = request.POST.get('capacity')
        type = request.POST.get('type')
        isActive = request.POST.get('isActive') == 'on'
        notes = request.POST.get('notes')

        Room.objects.create(
            roomCode=roomCode,
            building=building,
            capacity=capacity,
            type=type,
            isActive=isActive,
            notes=notes
        )

        messages.success(request, 'Room successfully added.')
        return redirect('roomList')

    return render(request, 'scheduling/rooms/create.html')


@login_required
@has_role('deptHead')
@transaction.atomic
def roomUpdate(request, roomId):
    room = get_object_or_404(Room, pk=roomId)

    if request.method == 'POST':
        room.roomCode = request.POST.get('roomCode')
        room.building = request.POST.get('building')
        room.capacity = request.POST.get('capacity')
        room.type = request.POST.get('type')
        room.isActive = request.POST.get('isActive') == 'on'
        room.notes = request.POST.get('notes')
        room.save()

        messages.success(request, 'Room updated successfully.')
        return redirect('roomList')

    return render(request, 'scheduling/rooms/update.html', {'room': room})


@login_required
@has_role('deptHead')
@transaction.atomic
def roomDelete(request, roomId):
    room = get_object_or_404(Room, pk=roomId)

    if request.method == 'POST':
        room.delete()
        messages.success(request, 'Room deleted.')
        return redirect('roomList')

    return render(request, 'scheduling/rooms/delete.html', {'room': room})
