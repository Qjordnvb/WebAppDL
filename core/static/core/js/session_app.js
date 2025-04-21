// core/static/core/js/session_app.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM Cargado. Iniciando JS de sesión.");

    // --- Obtener Session ID ---
    const sessionIdElement = document.getElementById('session-id');
    const sessionId = document.getElementById("session-id").textContent.trim();

    // --- Obtener elementos de la UI ---
    const currentUrlElement = document.getElementById('current-url');
    const browserStateElement = document.getElementById('browser-state');
    // *** Seleccionamos el contenedor de la lista de DataLayers ***
    const datalayerListElement = document.getElementById('datalayer-list');
    // *** Variable para saber si ya hemos limpiado el placeholder ***
    let datalayerPlaceholderRemoved = false;


    if (!sessionId) {
        console.error("¡Error crítico! No se pudo obtener el session_id del HTML.");
        if (browserStateElement) browserStateElement.textContent = "Error: Falta ID de Sesión";
        return;
    }

    console.log("Session ID:", sessionId);

    // --- Configuración WebSocket ---
    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    const wsURL = `${wsScheme}://${window.location.host}/ws/session/${sessionId}/`;
    let socket;

    function connectWebSocket() {
        console.log(`Intentando conectar a: ${wsURL}`);
        if (browserStateElement) browserStateElement.textContent = "Conectando...";

        socket = new WebSocket(wsURL);

        // --- Manejadores de Eventos WebSocket ---
        socket.onopen = (event) => {
            console.log("WebSocket Conectado!");
            if (browserStateElement) browserStateElement.textContent = "Conectado, inicializando navegador...";
            socket.send(JSON.stringify({
                action: "init_browser"
            }));
        };

        socket.onmessage = (event) => {
            console.log("Mensaje recibido:", event.data);
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                console.error("Error parseando mensaje JSON:", e);
                return;
            }

            // Procesar acción
            switch (data.action) {
                case "browser_state":
                    if (browserStateElement) browserStateElement.textContent = data.state || 'Desconocido';
                    break;
                case "browser_ready":
                    console.log("Browser listo:", data);
                    if (browserStateElement) browserStateElement.textContent = "Navegador Listo";
                    break;
                case "navigation_complete":
                    if (currentUrlElement) currentUrlElement.textContent = data.url || 'N/A';
                    if (browserStateElement) browserStateElement.textContent = "Listo"; // Más simple que 'Navegación Completa'
                    break;
                case "navigation_error":
                    if (browserStateElement) browserStateElement.textContent = `Error Navegación: ${data.error || 'Desconocido'}`;
                    console.error("Error de navegación recibido:", data);
                    break;
                case "error": // Errores generales del backend
                    if (browserStateElement) browserStateElement.textContent = `Error Backend: ${data.message || 'Desconocido'}`;
                    console.error("Error general recibido:", data);
                    break;

                // --- INICIO NUEVO MANEJADOR ---
                case "new_datalayer":
                    console.log("Nuevo DataLayer recibido:", data.payload);
                    if (datalayerListElement && data.payload) {
                        // Limpiar el mensaje "Esperando..." solo la primera vez
                        if (!datalayerPlaceholderRemoved) {
                            const placeholder = datalayerListElement.querySelector('.text-muted');
                            if (placeholder) {
                                placeholder.remove();
                            }
                            datalayerPlaceholderRemoved = true;
                        }

                        // Crear un nuevo elemento para mostrar el DataLayer
                        const dlElement = document.createElement('div');
                        dlElement.style.borderBottom = "1px solid #eee"; // Separador visual
                        dlElement.style.marginBottom = "10px";
                        dlElement.style.paddingBottom = "10px";

                        const preElement = document.createElement('pre');
                        preElement.style.whiteSpace = "pre-wrap"; // Para que el texto se ajuste
                        preElement.style.wordBreak = "break-all"; // Para romper palabras largas si es necesario
                        preElement.style.maxHeight = "200px"; // Limitar altura
                        preElement.style.overflowY = "auto"; // Scroll si es muy largo
                        preElement.style.backgroundColor = "#e9ecef"; // Fondo ligero
                        preElement.style.padding = "5px";
                        preElement.style.borderRadius = "4px";
                        preElement.style.fontSize = "0.85em";

                        // Formatear el JSON para mostrarlo bonito
                        preElement.textContent = JSON.stringify(data.payload, null, 2); // null, 2 para indentación

                        dlElement.appendChild(preElement);

                        // Añadir el nuevo elemento al PRINCIPIO de la lista
                        datalayerListElement.prepend(dlElement);

                    } else {
                        console.warn("No se pudo mostrar el DataLayer: contenedor no encontrado o payload vacío.");
                    }
                    break;
                // --- FIN NUEVO MANEJADOR ---

                default:
                    console.warn("Acción desconocida recibida del backend:", data.action);
            }
        };

        socket.onclose = (event) => {
            console.warn(`WebSocket Desconectado: Código=${event.code}, Razón='${event.reason}'`);
            if (browserStateElement) browserStateElement.textContent = `Desconectado (${event.code})`;
            // Intento de reconexión simple (opcional)
            // setTimeout(connectWebSocket, 5000);
        };

        socket.onerror = (error) => {
            console.error("Error WebSocket:", error);
            if (browserStateElement) browserStateElement.textContent = "Error de Conexión";
        };
    }

    // Iniciar la conexión WebSocket
    connectWebSocket();

});
