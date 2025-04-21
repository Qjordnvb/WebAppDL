# WebAppDL/core/controllers/browser_controller.py
import os
import json
import httpx
import asyncio
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class BrowserController:
    """
    Manages the lifecycle of a remote browser session using a standard
    WebDriver endpoint (like Selenium Standalone). Handles session creation,
    provides connection details, and ensures session termination.
    """
    def __init__(self, session_id: str, session_url: str, notify_callback=None):
        self.session_id = session_id # ID de la sesión de la app Django
        self.session_url = session_url # URL objetivo para la navegación
        self._state = "stopped"
        self._selenium_session_id: Optional[str] = None # ID de la sesión de Selenium/WebDriver
        self._cdp_url: Optional[str] = None
        self._vnc_info: Optional[str] = None # Info VNC (puerto/pass), no URL directa
        self.notify_client = notify_callback
        self._webdriver_base_url: Optional[str] = None # Guardar la URL base del WebDriver

    @property
    def state(self):
        return self._state

    def _get_webdriver_base_url(self) -> str:
        """Gets and validates the WebDriver base URL from environment variables."""
        if self._webdriver_base_url is None:
            # Lee la variable de entorno (que ahora apunta a selenium-chrome)
            url = os.environ.get("SELENOID_URL", "http://selenium-chrome:4444/wd/hub")
            if not url:
                logger.critical("SELENOID_URL (WebDriver URL) no está definida en el entorno.")
                raise ValueError("La URL base del WebDriver no está configurada.")
            self._webdriver_base_url = url.rstrip('/')
            logger.info(f"URL base de WebDriver configurada: {self._webdriver_base_url}")
        return self._webdriver_base_url

    async def get_selenium_session(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Creates a new Selenium session via standard WebDriver endpoint.

        Returns:
            Tuple containing (cdp_url, vnc_info, selenium_session_id) or raises error.
        """
        base_url = self._get_webdriver_base_url()
        session_creation_url = f"{base_url}/session"

        # Payload estándar W3C para Selenium Standalone con Chrome
        payload = {
            "capabilities": {
                "alwaysMatch": {
                    "browserName": "chrome",
                    # Opciones específicas de Chrome (ejemplo, ajustar si es necesario)
                    # "goog:chromeOptions": {
                    #    "args": ["--disable-gpu"]
                    # }
                }
            }
        }

        response = None
        try:
           async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
               logger.info(f"Creando sesión en WebDriver: {session_creation_url}")
               logger.debug(f"Payload de capacidades: {json.dumps(payload)}")
               response = await client.post(session_creation_url, json=payload)

           response.raise_for_status()

           if not response.text or not response.text.strip():
               logger.error(f"Respuesta vacía del servidor WebDriver. Status: {response.status_code}, Headers: {response.headers}")
               raise RuntimeError("Respuesta vacía o inesperada del servidor WebDriver.")

           try:
               data = response.json()
           except json.JSONDecodeError as e:
               logger.error(f"No se pudo decodificar JSON del WebDriver. Error: {e}. Respuesta: {response.text[:500]}...")
               raise RuntimeError("WebDriver no devolvió JSON válido") from e

           value_data = data.get("value")
           if not isinstance(value_data, dict):
               logger.error(f"Respuesta JSON no contiene un objeto 'value'. Respuesta: {data}")
               raise RuntimeError("Formato de respuesta JSON inesperado (falta 'value').")

           session_id = value_data.get("sessionId")
           capabilities = value_data.get("capabilities", {})

           if not session_id:
                logger.error(f"Respuesta JSON no contiene 'sessionId'. Respuesta: {data}")
                raise RuntimeError("Formato de respuesta JSON inesperado (falta 'sessionId').")

           self._selenium_session_id = session_id

           # Intentar obtener CDP (puede no estar siempre presente/accesible)
           self._cdp_url = capabilities.get("se:cdp")
           if not self._cdp_url and isinstance(capabilities.get("goog:chromeOptions"), dict):
                debugger_address = capabilities["goog:chromeOptions"].get("debuggerAddress")
                if debugger_address:
                   logger.warning(f"CDP disponible en {debugger_address} DENTRO del contenedor Selenium.")
                   # No se guarda self._cdp_url porque la dirección no es directamente usable por el contenedor web
                   # Se podría intentar exponer/mapear si fuera necesario.

           # VNC Info: Sabemos que está en el puerto 7900 del host, contraseña 'secret'
           self._vnc_info = "localhost:7900 (pass: secret)" # O la IP del host Docker

           logger.info(f"Sesión Selenium creada: ID={self._selenium_session_id}, VNC Info: {self._vnc_info}, CDP={self._cdp_url if self._cdp_url else 'No expuesto'}")
           return self._cdp_url, self._vnc_info, self._selenium_session_id

        except httpx.TimeoutException as e:
            logger.error(f"Timeout al conectar/crear sesión en WebDriver ({session_creation_url}).", exc_info=False)
            raise RuntimeError(f"Timeout al intentar crear sesión remota. Verifica el contenedor WebDriver.") from e
        except httpx.HTTPStatusError as e:
            raw_response_text = e.response.text if e.response else "N/A"
            logger.error(f"Error HTTP {e.response.status_code} al crear sesión WebDriver.")
            logger.error(f"Respuesta cruda: {raw_response_text[:500]}...", exc_info=False)
            raise RuntimeError(f"Error del servidor WebDriver ({e.response.status_code}): No se pudo crear sesión.") from e
        except (json.JSONDecodeError, RuntimeError, ValueError) as e:
             raw_response_text = response.text if response else "N/A"
             logger.error(f"Error procesando respuesta o configuración de WebDriver: {e}")
             if response: logger.error(f"Respuesta cruda: {raw_response_text[:500]}...", exc_info=False)
             raise RuntimeError(f"Error procesando respuesta/configuración de WebDriver: {e}") from e
        except Exception as e:
            raw_response_text = response.text if response else "N/A"
            logger.error(f"Error inesperado al crear sesión WebDriver. Respuesta cruda: {raw_response_text[:500]}...", exc_info=True)
            raise RuntimeError(f"No se pudo crear la sesión remota (Error: {type(e).__name__})") from e

    async def start_and_navigate(self, url_to_navigate: str):
        """Starts the browser session and potentially navigates."""
        if self._state != "stopped":
            logger.warning(f"Intento de iniciar un navegador que no está detenido (estado: {self._state})")
            return

        self._state = "starting"
        logger.info(f"Iniciando navegador para URL: {url_to_navigate}")

        try:
            cdp_url, vnc_info, session_id = await self.get_selenium_session()
            self._state = "running"

            logger.info(f"Navegador listo. Notificando al cliente. VNC Info: {vnc_info}")

            if self.notify_client:
                await self.notify_client("browser_ready", {
                    "selenium_session_id": session_id,
                    "cdp_url": cdp_url,
                    "vnc_info": vnc_info, # Pasamos la info, no una URL directa
                    "target_url": url_to_navigate
                })

            # --- LÓGICA DE NAVEGACIÓN Y CAPTURA IRÍA AQUÍ ---
            # Esta lógica DEBERÍA funcionar ahora usando librerías Selenium estándar
            # conectándose a la URL base del WebDriver y usando el session_id obtenido.
            # logger.info(f"Iniciando navegación a {url_to_navigate}...")
            # await self.perform_navigation_and_capture(url_to_navigate) # Función hipotética

        except Exception as e:
            self._state = "error"
            logger.error(f"Error durante el inicio del navegador para sesión {self.session_id}: {e}", exc_info=True)
            if self.notify_client:
                await self.notify_client("error", {
                    "message": f"Fallo al iniciar el navegador: {type(e).__name__}. Revisa los logs.",
                })

    async def stop(self):
        """Stops the remote browser session by sending DELETE to WebDriver endpoint."""
        if self._state in ["stopped", "stopping"]:
             logger.info(f"Controlador ya está detenido o deteniéndose (estado: {self._state}).")
             return

        logger.info(f"Deteniendo sesión remota Selenium (ID: {self._selenium_session_id})...")
        self._state = "stopping"

        if not self._selenium_session_id:
            logger.warning("No hay ID de sesión de Selenium para detener.")
            self._state = "stopped"
            return

        base_url = self._get_webdriver_base_url() # Obtiene http://selenium-chrome:4444/wd/hub
        session_delete_url = f"{base_url}/session/{self._selenium_session_id}"
        logger.info(f"Enviando DELETE a WebDriver: {session_delete_url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(session_delete_url)
            response.raise_for_status()
            logger.info(f"Sesión Selenium {self._selenium_session_id} eliminada correctamente.")
        except httpx.RequestError as e:
             logger.error(f"Error de red al intentar eliminar sesión {self._selenium_session_id}: {e}")
        except httpx.HTTPStatusError as e:
             if e.response.status_code == 404:
                 logger.warning(f"Sesión {self._selenium_session_id} no encontrada en WebDriver (quizás ya terminó). Status: 404")
             else:
                 logger.error(f"Error HTTP {e.response.status_code} al eliminar sesión {self._selenium_session_id}. Respuesta: {e.response.text[:500]}...")
        except Exception as e:
             logger.error(f"Error inesperado al eliminar sesión {self._selenium_session_id}", exc_info=True)
        finally:
             self._selenium_session_id = None
             self._cdp_url = None
             self._vnc_info = None
             self._state = "stopped"
             logger.info("Controlador marcado como detenido.")
