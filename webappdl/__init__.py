# webappdl/__init__.py

# Esto asegurará que la app Celery siempre se importe cuando Django inicie
# para que las tareas compartidas (@shared_task) usen esta app.
from .celery import app as celery_app

__all__ = ("celery_app",)
