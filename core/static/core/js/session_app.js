// core/static/core/js/session_app.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM Cargado. Iniciando JS de sesión (Polling Version).");

    // --- Obtener Session ID y URL de Status ---
    const sessionId = JSON.parse(document.getElementById('session-id-data').textContent);
    const statusUrl = JSON.parse(document.getElementById('status-url-data').textContent);

    // --- Obtener elementos de la UI ---
    const statusElement = document.getElementById('session-status');
    const vncLinkContainer = document.getElementById('vnc-link-container');
    const vncLinkElement = document.getElementById('vnc-link');
    const finishButtonContainer = document.getElementById('finish-button-container');
    const finishButton = document.getElementById('finish-button');
    const reportLinkContainer = document.getElementById('report-link-container');
    const reportLinkElement = document.getElementById('report-link');

    let pollingIntervalId = null; // Variable para guardar el ID del intervalo
    const POLLING_INTERVAL_MS = 3000; // Consultar cada 3 segundos

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
            // --- INICIO: Bloque Simplificado ---
            if (data.vnc_url && vncLinkElement && vncLinkContainer) {
                // Ahora data.vnc_url contiene la URL directa, la usamos tal cual
                console.log("VNC URL recibida:", data.vnc_url); // Log para verificar
                vncLinkElement.href = data.vnc_url;
                vncLinkContainer.style.display = 'block'; // Mostrar contenedor del botón
            } else {
                 console.warn("vnc_url no recibida o elementos no encontrados.");
                 vncLinkContainer.style.display = 'none'; // Ocultar si no hay URL
            }
            // --- FIN: Bloque Simplificado ---

            if (finishButton) finishButton.disabled = false; // Habilitar botón Finalizar
             if (finishButtonContainer) finishButtonContainer.style.display = 'block';

        } else {
            // Ocultar enlace y deshabilitar/ocultar botón si no está esperando al usuario
            if (vncLinkContainer) vncLinkContainer.style.display = 'none';
            if (finishButton) finishButton.disabled = true;
             if(['processing', 'completed', 'error', 'finish_requested'].includes(data.status_code)) {
                 if (finishButtonContainer) finishButtonContainer.style.display = 'none';
             } else {
                 if (finishButtonContainer) finishButtonContainer.style.display = 'block';
             }
        }

        // Mostrar enlace al reporte si está completado
        if (data.status_code === 'completed') {
             // Asumimos que el backend devolverá 'report_url' en el futuro
             const reportUrl = data.report_url; // NECESITAREMOS AÑADIR ESTO A LA RESPUESTA JSON
             if(reportUrl && reportLinkContainer && reportLinkElement) {
                 reportLinkElement.href = reportUrl;
                 reportLinkContainer.style.display = 'block';
             } else {
                  reportLinkContainer.style.display = 'none';
             }
             stopPolling(); // Detener polling si está completado
        } else {
             if (reportLinkContainer) reportLinkContainer.style.display = 'none';
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
                // Considerar detener el polling si hay errores repetidos
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

    // --- Iniciar Polling ---
    // Hacer una llamada inicial inmediata
    pollStatus();
    // Establecer el intervalo para llamadas periódicas
    pollingIntervalId = setInterval(pollStatus, POLLING_INTERVAL_MS);

    // --- Lógica para el botón Finalizar (se añadirá en Paso 7) ---
    // if (finishButton) {
    //     finishButton.addEventListener('click', () => {
    //         // Aquí irá la lógica para llamar a la vista finish_session_view
    //         console.log("Botón Finalizar clickeado - Lógica pendiente");
    //         finishButton.disabled = true; // Deshabilitar al hacer click
    //         if (statusElement) statusElement.textContent = "Finalización solicitada...";
    //         stopPolling(); // Detener polling al finalizar manualmente
    //         // Llamada fetch POST a la URL de finalización...
    //     });
    // }

    // --- Limpieza al salir de la página (opcional) ---
    // window.addEventListener('beforeunload', () => {
    //     stopPolling();
    // });

});
