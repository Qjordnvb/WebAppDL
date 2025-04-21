# core/routing.py
from django.urls import re_path

from . import consumers # Importa tus consumidores de la app core

websocket_urlpatterns = [
    # Asegúrate de que la ruta coincida con la URL que usas en tu JS del frontend
    # Ejemplo: ws://localhost:8000/ws/session/TU_SESSION_ID/
    re_path(r'ws/session/(?P<session_id>[^/]+)/$', consumers.SessionConsumer.as_asgi()),
]
