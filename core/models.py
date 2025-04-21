# core/models.py
import uuid
from django.db import models

class Session(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('active', 'Activa'),
        ('error', 'Error'),
        ('completed', 'Completada'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.URLField(max_length=2000, help_text="URL del sitio a validar")
    # Guardamos el JSON como texto, podrías usar FileField si prefieres manejar archivos
    reference_json_content = models.TextField(help_text="Contenido del JSON de referencia")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Podrías añadir más campos como 'description', 'user', etc.

    def __str__(self):
        return f"Session {self.id} for {self.url}"

# Más adelante añadiremos modelos para DataLayerCapture, Screenshot, Report, etc.
