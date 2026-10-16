# core/views.py
import logging
import json # Añadido por si se necesita en el futuro, aunque no para finish_session_view
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
# from django.views.decorators.csrf import csrf_protect # Middleware CSRF suele ser suficiente
from django.db import transaction
from django.utils import timezone # Para actualizar 'updated_at' explícitamente si es necesario

from .forms import StartSessionForm
from .models import Session
from .tasks import run_selenium_validation # Importa la tarea Celery

# Configura el logger para este módulo
logger = logging.getLogger(__name__)

def start_session_view(request):
    """
    Maneja el formulario para iniciar una nueva sesión de validación.
    """
    if request.method == 'POST':
        form = StartSessionForm(request.POST)
        if form.is_valid():
            # Crear el objeto Session
            try:
                # El form ya valida que sea JSON, aquí lo cargamos si es necesario
                # o lo guardamos directamente si el modelo es JSONField
                schema_data = json.loads(form.cleaned_data["reference_schema"])
            except json.JSONDecodeError:
                # Esto no debería ocurrir si la validación del form funciona
                form.add_error("reference_schema", "Error interno al procesar el JSON.")
                return render(request, "core/start_session_form.html", {"form": form})

            try:
                new_session = Session.objects.create(
                    url=form.cleaned_data["url"],
                    reference_schema=schema_data, # Guardar JSON parseado
                    # description=form.cleaned_data.get('description'), # Añadir si tienes campo description
                    status=Session.STATUS_PENDING, # Estado inicial
                )

                # Lanzar la tarea Celery en segundo plano
                run_selenium_validation.delay(new_session.pk)
                logger.info(
                    f"Tarea Celery 'run_selenium_validation' lanzada para Session PK: {new_session.pk}"
                )
                # Redirigir a la página de la sesión recién creada
                return redirect('session_page', session_id=new_session.id)

            except Exception as e:
                 # Manejar error al crear sesión o lanzar tarea
                 logger.exception(f"Error creando sesión o lanzando tarea Celery: {e}")
                 # Añadir mensaje de error genérico al formulario o contexto
                 context = {'form': form, 'error_message': 'Ocurrió un error al iniciar la sesión. Inténtalo de nuevo.'}
                 return render(request, 'core/start_session_form.html', context, status=500)
        else:
             # Formulario inválido, renderizar de nuevo con errores
             return render(request, "core/start_session_form.html", {"form": form})
    else:
        # Petición GET, mostrar formulario vacío
        form = StartSessionForm()

    return render(request, 'core/start_session_form.html', {'form': form})

def session_page_view(request, session_id):
    """
    Muestra la página de estado y control para una sesión específica.
    """
    session_obj = get_object_or_404(Session, pk=session_id)
    # Pasa el estado inicial también para evitar un pequeño delay hasta el primer polling
    initial_status = session_obj.get_status_display()
    context = {
        'session_id': session_obj.id,
        'session_url': session_obj.url,
        'initial_status': initial_status, # Añadido estado inicial
        # Puedes pasar más datos si los necesitas de inmediato en la plantilla
    }
    return render(request, 'core/session_page.html', context)


def get_session_status(request, session_id):
    """
    Devuelve el estado actual, URL VNC y URL del reporte (si existe) en JSON.
    Usado por el polling AJAX del frontend.
    """
    session_obj = get_object_or_404(Session, pk=session_id)
    report_url = None
    # Obtener URL del reporte solo si existe el archivo y el estado es completado
    # Se implementará la lógica de report_file en Paso 8 y 9
    if session_obj.status == Session.STATUS_COMPLETED and session_obj.report_file:
        try:
            # build_absolute_uri es útil si necesitas la URL completa incluyendo dominio
            # report_url = request.build_absolute_uri(session_obj.report_file.url)
            # O simplemente la URL relativa si el frontend está en el mismo dominio
             report_url = session_obj.report_file.url
        except ValueError:
             # report_file podría no estar asociado a storage si no se guardó correctamente
             logger.error(f"No se pudo obtener URL para report_file de sesión {session_id}. ¿Archivo guardado correctamente?")
             report_url = None
        except Exception as e:
             logger.error(f"Error generando URL para report_file de sesión {session_id}: {e}")
             report_url = None

    data = {
        "status": session_obj.get_status_display(), # Texto legible del estado
        "status_code": session_obj.status,       # Código interno del estado
        "vnc_url": session_obj.vnc_url,           # URL VNC si existe
        "report_url": report_url                  # URL del reporte si existe y está completado
    }
    return JsonResponse(data)


# --- NUEVA VISTA PARA FINALIZAR LA SESIÓN ---
@require_POST # Asegura que esta vista solo acepte peticiones POST
# @csrf_protect # Usualmente no necesario si el middleware CSRF está habilitado globalmente
def finish_session_view(request, session_id):
    """
    Endpoint para que el usuario solicite finalizar la fase interactiva.
    Cambia el estado de la sesión a 'FINISH_REQUESTED'.
    """
    logger.info(f"Recibida solicitud POST para finalizar sesión interactiva: {session_id}")
    try:
        # Usar transacción para asegurar consistencia al leer y actualizar
        with transaction.atomic():
            # Obtener la sesión y bloquearla para evitar condiciones de carrera
            session_obj = get_object_or_404(Session.objects.select_for_update(), pk=session_id)

            # Verificar que la sesión esté en el estado correcto para ser finalizada
            if session_obj.status != Session.STATUS_WAITING_USER:
                logger.warning(f"Intento de finalizar sesión {session_id} en estado inválido: {session_obj.status}")
                return JsonResponse({
                    'status': 'error',
                    'error': f'La sesión no está esperando al usuario (estado actual: {session_obj.get_status_display()}). No se puede finalizar.'
                }, status=409) # 409 Conflict - Estado incorrecto

            # Actualizar el estado a 'Finalización Solicitada'
            session_obj.status = Session.STATUS_FINISH_REQUESTED
            # Opcional: Forzar actualización de 'updated_at' aunque solo cambie el estado
            # session_obj.updated_at = timezone.now()
            session_obj.save(update_fields=['status', 'updated_at'])
            logger.info(f"Sesión {session_id} actualizada a estado: {Session.STATUS_FINISH_REQUESTED}")

        # Devolver respuesta de éxito
        return JsonResponse({'status': 'ok', 'message': 'Solicitud de finalización recibida. Procesando...'})

    except Session.DoesNotExist:
         logger.warning(f"Solicitud para finalizar sesión no encontrada: {session_id}")
         return JsonResponse({'status': 'error', 'error': 'Sesión no encontrada.'}, status=404) # 404 Not Found
    except Exception as e:
        # Capturar cualquier otro error inesperado durante el proceso
        logger.exception(f"Error inesperado en finish_session_view para sesión {session_id}: {e}")
        return JsonResponse({'status': 'error', 'error': 'Error interno del servidor al procesar la solicitud de finalización.'}, status=500) # 500 Internal Server Error
