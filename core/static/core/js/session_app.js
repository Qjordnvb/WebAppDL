// core/static/core/js/session_app.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM Cargado. Iniciando JS de sesión (Polling Version).");

    // --- Obtener Session ID y URL de Status ---
    const sessionId = JSON.parse(document.getElementById('session-id-data').textContent);
    const statusUrl = JSON.parse(document.getElementById('status-url-data').textContent);

    // --- Obtener elementos de la UI ---
    const statusElement = document.getElementById('session-status');
    const vncLinkContainer = document.getElementById('vnc-link-container'); // Contenedor para el enlace VNC
    const vncLinkElement = document.getElementById('vnc-link'); // Elemento <a> del enlace VNC
    const finishButtonContainer = document.getElementById('finish-button-container');
    const finishButton = document.getElementById('finish-button');
    const reportLinkContainer = document.getElementById('report-link-container');
    const reportLinkElement = document.getElementById('report-link');

    let pollingIntervalId = null;
    const POLLING_INTERVAL_MS = 3000; // Consultar cada 3 segundos

    // --- URL para finalizar la sesión ---
    const finishUrl = `/session/${sessionId}/finish/`; // URL que crearemos en Django
    const csrfToken = getCookie('csrftoken'); // Obtener token CSRF para POST

    if (!sessionId || !statusUrl) {
        console.error("¡Error crítico! Falta session_id o status_url.");
        if (statusElement) statusElement.textContent = "Error de Configuración";
        return;
    }

    console.log("Session ID:", sessionId);
    console.log("Status URL:", statusUrl);

    // --- Función para actualizar UI basada en datos ---
    function updateUI(data) {
        if (!data) return;

        // Actualizar texto de estado
        if (statusElement) {
            statusElement.textContent = data.status || 'Desconocido';
        }

        // Mostrar/Ocultar enlace VNC y habilitar/deshabilitar botón Finalizar
        if (data.status_code === 'waiting_user') {
            // Mostrar enlace VNC y botón Finalizar
            if (data.vnc_url && vncLinkElement && vncLinkContainer) {
                console.log("VNC URL recibida:", data.vnc_url);
                vncLinkElement.href = data.vnc_url;
                vncLinkContainer.style.display = 'block'; // Mostrar contenedor del botón VNC
                if(finishButtonContainer) finishButtonContainer.style.display = 'block'; // Mostrar botón finalizar
            } else {
                 console.warn("vnc_url no recibida o elementos VNC no encontrados.");
                 if (vncLinkContainer) vncLinkContainer.style.display = 'none';
                 if (finishButtonContainer) finishButtonContainer.style.display = 'none'; // Ocultar también finalizar si VNC no está listo
            }
            // Habilitar botón Finalizar
            if (finishButton) finishButton.disabled = false;

        } else {
            // Ocultar enlace VNC y deshabilitar/ocultar botón si no está esperando
            if (vncLinkContainer) vncLinkContainer.style.display = 'none';

            if (finishButton) finishButton.disabled = true;
            // Ocultar contenedor del botón si ya no aplica (procesando, completado, error, etc.)
            if(['processing', 'completed', 'error', 'finish_requested'].includes(data.status_code)) {
                 if (finishButtonContainer) finishButtonContainer.style.display = 'none';
            } else {
                 // Mantener visible pero deshabilitado en otros estados iniciales si es necesario
                 if (finishButtonContainer) finishButtonContainer.style.display = 'block';
            }
        }

        // Mostrar enlace al reporte si está completado
        if (data.status_code === 'completed') {
             const reportUrl = data.report_url; // Obtener URL del backend (se añadirá en Paso 9)
             if(reportUrl && reportLinkContainer && reportLinkElement) {
                 console.log("Report URL recibido:", reportUrl);
                 reportLinkElement.href = reportUrl;
                 reportLinkContainer.style.display = 'block'; // Mostrar contenedor del reporte
             } else {
                  // console.warn("Report URL no disponible o elementos no encontrados."); // Descomentar para debug
                  reportLinkContainer.style.display = 'none'; // Ocultar si no hay URL/elementos
             }
             stopPolling(); // Detener polling si está completado
        } else {
             if (reportLinkContainer) reportLinkContainer.style.display = 'none'; // Ocultar si no está completado
        }

        // Detener polling si hay error final
        if (data.status_code === 'error') {
             stopPolling();
        }
    }

    // --- Función para realizar la consulta AJAX (Polling) ---
    function pollStatus() {
        console.log("Polling status...");
        fetch(statusUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log("Status data received:", data);
                updateUI(data);
            })
            .catch(error => {
                console.error('Error durante polling:', error);
                if (statusElement) statusElement.textContent = "Error consultando estado...";
                // Considerar detener el polling si hay errores repetidos o cambiar lógica
                // stopPolling();
            });
    }

    // --- Función para detener el polling ---
    function stopPolling() {
        if (pollingIntervalId) {
            console.log("Deteniendo polling.");
            clearInterval(pollingIntervalId);
            pollingIntervalId = null;
        }
    }

    // --- Lógica para el botón Finalizar ---
    if (finishButton) {
        finishButton.addEventListener('click', () => {
            console.log("Botón Finalizar clickeado.");
            finishButton.disabled = true; // Deshabilitar inmediatamente
            if (statusElement) statusElement.textContent = "Finalización solicitada...";
            stopPolling(); // Detener polling al finalizar manualmente

            // Enviar petición POST para cambiar el estado
            fetch(finishUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken // Incluir token CSRF (requiere getCookie)
                },
                // No es necesario enviar body si toda la info está en la URL
            })
            .then(response => {
                // Verificar si la respuesta fue OK (status 2xx)
                if (!response.ok) {
                    console.error('Error al solicitar finalización:', response.status, response.statusText);
                    // Intenta leer el cuerpo del error como JSON
                    return response.json().then(errData => {
                       // Lanza un error que incluya el mensaje del backend si existe
                       throw new Error(errData.error || `Error del servidor: ${response.status}`);
                    }).catch(() => {
                        // Si el cuerpo no es JSON o hay otro error al leerlo, lanza error genérico
                        throw new Error(`Error del servidor: ${response.status} ${response.statusText}`);
                    });
                }
                // Si la respuesta fue OK, parsear el JSON
                return response.json();
            })
            .then(data => {
                // Verificar si la respuesta JSON indica éxito
                if(data && data.status === 'ok'){
                    console.log("Solicitud de finalización enviada con éxito.");
                    // Actualizamos estado visualmente ya que detuvimos el polling
                    if (statusElement) statusElement.textContent = "Procesando...";
                } else {
                    // Manejar caso donde el status es 2xx pero el JSON no indica 'ok' o tiene un error
                    const errorMessage = data ? data.error : 'Respuesta inesperada del servidor.';
                    console.error("Respuesta inesperada/error del servidor al finalizar:", errorMessage);
                    alert(`Error al finalizar: ${errorMessage}`);
                    if (statusElement) statusElement.textContent = `Error: ${errorMessage}`;
                    // Podrías rehabilitar el botón aquí si el estado no cambió
                    // finishButton.disabled = false;
                }
            })
            .catch(error => {
                // Capturar errores de red o errores lanzados desde .then()
                console.error('Error en fetch o procesamiento de respuesta al finalizar:', error);
                if (statusElement) statusElement.textContent = "Error al procesar finalización...";
                alert(`Error al finalizar la sesión: ${error.message || error}`);
                // Considera rehabilitar el botón en caso de error de red
                // finishButton.disabled = false;
            });
        });
    }

    // --- Iniciar Polling ---
    pollStatus(); // Llamada inicial
    pollingIntervalId = setInterval(pollStatus, POLLING_INTERVAL_MS); // Iniciar ciclo

    // --- Función auxiliar para obtener el token CSRF de las cookies ---
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                // Does this cookie string begin with the name we want?
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        if (!cookieValue) {
            console.warn('CSRF token cookie not found. POST requests might fail.');
        }
        return cookieValue;
    }

}); // Fin DOMContentLoaded
