# core/models.py
import uuid
from django.db import models

# Opcional: Importar User si quieres asociar sesiones a usuarios de Django/Wagtail
# from django.contrib.auth.models import User
# from django.conf import settings # Si usas settings.AUTH_USER_MODEL


class Session(models.Model):
    # Definir constantes para los estados
    STATUS_PENDING = "pending"
    STATUS_STARTING = "starting"
    STATUS_WAITING_USER = "waiting_user"
    STATUS_FINISH_REQUESTED = "finish_requested"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_ERROR = "error"

    # Opciones para el campo status
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_STARTING, "Iniciando"),
        (STATUS_WAITING_USER, "Esperando Usuario"),
        (STATUS_FINISH_REQUESTED, "Finalización Solicitada"),
        (STATUS_PROCESSING, "Procesando"),
        (STATUS_COMPLETED, "Completada"),
        (STATUS_ERROR, "Error"),
    ]

    # --- Campos Existentes ---
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.URLField(max_length=2000, help_text="URL del sitio a validar")
    # Cambiamos a JSONField para el schema y otros datos estructurados
    reference_schema = models.JSONField(
        help_text="Schema JSON de referencia para la validación (generado desde el input)",
        null=True,
        blank=True,  # Permitir null temporalmente hasta que lo poblemos
    )
    status = models.CharField(
        max_length=20,  # Aumentar longitud para nuevos estados
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Nuevos Campos ---
    # user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='validation_sessions') # Opcional: Asociar a usuario
    vnc_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        help_text="URL para acceder a la sesión VNC del navegador remoto",
    )
    selenium_session_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="ID de la sesión específica en Selenium Grid/Standalone",
    )
    captured_data = models.JSONField(
        null=True,
        blank=True,
        help_text="DataLayers capturados durante la sesión interactiva",
    )
    validation_results = models.JSONField(
        null=True,
        blank=True,
        help_text="Resultados detallados de la validación vs el schema",
    )
    # Usamos FileField para guardar el reporte generado
    # Necesitarás configurar MEDIA_ROOT y MEDIA_URL en settings.py
    report_file = models.FileField(
        upload_to="validation_reports/",  # Se guardará en MEDIA_ROOT/validation_reports/
        null=True,
        blank=True,
        help_text="Archivo del reporte de validación generado",
    )
    # Eliminamos reference_json_content ya que usaremos reference_schema (JSONField)

    def __str__(self):
        return f"Session {self.id} for {self.url} [{self.status}]"

    class Meta:
        ordering = [
            "-created_at"
        ]  # Ordenar por defecto por fecha de creación descendente
