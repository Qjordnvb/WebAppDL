# webappdl/celery.py
import os
from celery import Celery

# Establece la variable de entorno por defecto para que Celery sepa dónde encontrar la configuración de Django.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webappdl.settings")

# Crea la instancia de la aplicación Celery. 'webappdl' es el nombre de tu proyecto.
app = Celery("webappdl")

# Carga la configuración de Celery desde los settings de Django.
# El namespace 'CELERY' significa que todas las claves de configuración de Celery en settings.py deben empezar con 'CELERY_'
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-descubre tareas en todas las aplicaciones Django instaladas (buscará archivos tasks.py).
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
