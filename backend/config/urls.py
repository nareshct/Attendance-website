"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    SearchView,
    UpdateEmailView,
)

admin.site.site_header = 'Apex Binary Admin'
admin.site.site_title = 'Apex Binary Admin'
admin.site.index_title = 'Administration'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/login/', LoginView.as_view(), name='auth-login'),
    path('api/auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('api/auth/change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('api/auth/me/', MeView.as_view(), name='auth-me'),
    path('api/auth/update-email/', UpdateEmailView.as_view(), name='auth-update-email'),
    path('api/auth/password-reset/', PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('api/auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    path('api/search/', SearchView.as_view(), name='search'),
    path('api/', include('students.urls')),
    path('api/', include('trainers.urls')),
    path('api/', include('clients.urls')),
    path('api/', include('courses.urls')),
    path('api/', include('enrollments.urls')),
    path('api/', include('attendance.urls')),
    path('api/', include('billing.urls')),
    path('api/', include('reports.urls')),
    path('api/', include('audit.urls')),
    path('api/', include('batches.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
