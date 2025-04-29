# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Ruta para el formulario de inicio de sesión (raíz de la app core)
    path("", views.start_session_view, name="start_session"),

    # Ruta para la página específica de una sesión
    path("session/<uuid:session_id>/", views.session_page_view, name="session_page"),

    # Ruta para obtener el estado de la sesión (usada por AJAX/Polling)
    path("session/<uuid:session_id>/status/", views.get_session_status, name="get_session_status"),

    # --- NUEVA RUTA PARA FINALIZAR LA SESIÓN ---
    path("session/<uuid:session_id>/finish/", views.finish_session_view, name="finish_session"),
]
