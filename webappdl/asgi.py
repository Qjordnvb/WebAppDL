# webappdl/asgi.py
import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application
import core.routing # Importaremos esto luego

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'webappdl.settings')

# Obtener la aplicación HTTP de Django estándar
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    # Manejo HTTP estándar de Django
    "http": django_asgi_app,

    # Manejo WebSocket
    "websocket": AllowedHostsOriginValidator(
        URLRouter(
            core.routing.websocket_urlpatterns # Definiremos esto en core/routing.py
        )
    ),
})
