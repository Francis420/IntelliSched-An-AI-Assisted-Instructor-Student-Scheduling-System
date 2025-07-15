from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test



# ---------- Access Control ----------
def isSysAdmin(user):
    return user.role == 'sysAdmin'


