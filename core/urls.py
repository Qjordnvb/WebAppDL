# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.start_session_view, name="start_session"),  # Página del formulario
    path(
        "session/<uuid:session_id>/", views.session_page_view, name="session_page"
    ),  # Página de la sesión
    path(
        "session/<uuid:session_id>/status/",
        views.get_session_status,
        name="get_session_status",
    ),
]
