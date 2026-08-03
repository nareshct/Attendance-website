from django.urls import path

from .views import (
    AttendanceReportView,
    ClientAttendanceReportView,
    ClientReportView,
    PayoutsReportView,
)

urlpatterns = [
    path('reports/payouts/', PayoutsReportView.as_view(), name='report-payouts'),
    path('reports/attendance/', AttendanceReportView.as_view(), name='report-attendance'),
    path('reports/client/<int:client_id>/', ClientReportView.as_view(), name='report-client'),
    path('reports/client/<int:client_id>/attendance/', ClientAttendanceReportView.as_view(), name='report-client-attendance'),
]
