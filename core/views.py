# core/views.py
from asyncio.log import logger
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .forms import StartSessionForm
from .models import Session
import json

from .tasks import run_selenium_validation

def start_session_view(request):
    if request.method == 'POST':
        form = StartSessionForm(request.POST)
        if form.is_valid():
            # Crear el objeto Session
            try:
                schema_data = json.loads(form.cleaned_data["reference_schema"])
            except json.JSONDecodeError:
                # Esto no debería pasar si la validación del form funcionó, pero por si acaso
                # Manejar el error apropiadamente, quizás renderizando el form con error
                form.add_error("reference_schema", "Error interno al procesar el JSON.")
                return render(request, "core/start_session_form.html", {"form": form})

            new_session = Session.objects.create(
                url=form.cleaned_data["url"],
                reference_schema=schema_data,  # <-- Usar el nuevo nombre y los datos parseados
                # description=form.cleaned_data.get('description'), # <-- Usar .get() si es opcional
                status=Session.STATUS_PENDING,  # Usar la constante definida en el modelo
            )

            run_selenium_validation.delay(new_session.pk)
            logger.info(
                f"Tarea Celery 'run_selenium_validation' lanzada para Session PK: {new_session.pk}"
            )
            # Redirigir a la página de la sesión recién creada
            return redirect('session_page', session_id=new_session.id)
    else:
        form = StartSessionForm()

    return render(request, 'core/start_session_form.html', {'form': form})

def session_page_view(request, session_id):
    # Obtener la sesión o mostrar error 404 si no existe
    session_obj = get_object_or_404(Session, pk=session_id)
    context = {
        'session_id': session_obj.id,
        'session_url': session_obj.url,
        # Puedes pasar más datos de la sesión si los necesitas en la plantilla
    }
    return render(request, 'core/session_page.html', context)


def get_session_status(request, session_id):
    """Devuelve el estado actual y la URL VNC de la sesión en formato JSON."""
    session_obj = get_object_or_404(Session, pk=session_id)
    data = {
        "status": session_obj.get_status_display(),  # Devuelve el texto legible del estado
        "status_code": session_obj.status,  # Devuelve el código interno del estado
        "vnc_url": session_obj.vnc_url,  # Devuelve la URL VNC si existe
        # Podríamos añadir más datos si fueran necesarios (ej. resultados parciales)
    }
    return JsonResponse(data)
