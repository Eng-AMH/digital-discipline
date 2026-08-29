from django.urls import path

from apps.devices import views

urlpatterns = [
    path("server-public-key/", views.ServerPublicKeyView.as_view(), name="server-public-key"),
    path("", views.DeviceListView.as_view(), name="device-list"),
    path("register/", views.DeviceRegisterView.as_view(), name="device-register"),
    path("<uuid:device_id>/", views.DeviceRemoveView.as_view(), name="device-remove"),
    path("<uuid:device_id>/heartbeat/", views.DeviceHeartbeatView.as_view(), name="device-heartbeat"),
    path("<uuid:device_id>/activity-sync/", views.ActivityLogBatchSyncView.as_view(), name="device-activity-sync"),
    path("<uuid:device_id>/events-sync/", views.DeviceEventBatchSyncView.as_view(), name="device-events-sync"),
]
