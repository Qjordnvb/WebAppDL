# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from .forms import StartSessionForm
from .models import Session
import json

def start_session_view(request):
    if request.method == 'POST':
        form = StartSessionForm(request.POST)
        if form.is_valid():
            # Crear el objeto Session
            new_session = Session.objects.create(
                url=form.cleaned_data['url'],
                reference_json_content=form.cleaned_data['reference_json_content'],
                # description=form.cleaned_data['description'] # Descomentar si añades descripción al modelo
                status='pending'
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
