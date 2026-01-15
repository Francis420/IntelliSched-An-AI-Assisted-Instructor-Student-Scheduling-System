from django.contrib import admin
from django.urls import path, include
from core.views import home
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from core.forms import CustomPasswordResetForm

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('auth/', include('authapi.urls')),
    path('core/', include('core.urls')),
    path('instructors/', include('instructors.urls')),
    path('scheduling/', include('scheduling.urls')),
    path('aimatching/', include('aimatching.urls')),
    path('scheduler/', include('scheduler.urls')),

    # 1. Request Password Reset
    path('passwordReset/', auth_views.PasswordResetView.as_view(template_name='registration/passwordResetForm.html', email_template_name='registration/passwordResetEmail.html', form_class=CustomPasswordResetForm), name='password_reset'),
    # 2. Email Sent Success
    path('passwordReset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/passwordResetDone.html'), name='password_reset_done'),
    # 3. Link Clicked -> Enter New Password
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/passwordResetConfirm.html'), name='password_reset_confirm'),
    # 4. Success Message
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/passwordResetComplete.html'), name='password_reset_complete'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
