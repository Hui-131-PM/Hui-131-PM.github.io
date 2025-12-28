# sensor/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('ingest/', views.ingest, name='sensor_ingest'),
    path('series/', views.series, name='sensor_series'),
]
