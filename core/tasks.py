# core/tasks.py
import logging

# import httpx # Ya no se usa httpx
import json
import time

from celery import shared_task
from django.conf import settings
from django.db import transaction

# Importaciones de Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    NoSuchWindowException,
)

from .models import Session  # Importar modelo Session

logger = logging.getLogger(__name__)

# --- Constantes o Configuraciones ---
VNC_PASSWORD = "secret"
# SELENIUM_HOST ya no es necesaria aquí si get_vnc_url no la usa
STATUS_CHECK_INTERVAL_SECONDS = 3
SELENIUM_COMMAND_TIMEOUT_SECONDS = 120

# --- Script JavaScript (sin cambios) ---
JS_CAPTURE_DATALAYER = """
(() => {
    const LS_KEY = 'capturedDataLayersLs'; window.capturedDataLayers = [];
    try { const existingData = localStorage.getItem(LS_KEY); if (existingData) { const parsedData = JSON.parse(existingData); if (Array.isArray(parsedData)) { window.capturedDataLayers = parsedData; console.log('Loaded ' + parsedData.length + ' from LS.'); } }
    } catch (e) { console.error('Error reading LS:', e); }
    window.dataLayer = window.dataLayer || []; const originalPush = window.dataLayer.push; let initialItemsProcessed = false; const initialTimestamp = Date.now();
    if (Array.isArray(window.dataLayer) && window.dataLayer.length > 0) { let addedFromInitial = 0; window.dataLayer.forEach(obj => { if (typeof obj !== 'undefined' && obj !== null && typeof obj._captureTimestamp === 'undefined') { try { const clone = JSON.parse(JSON.stringify(obj)); clone._captureTimestamp = initialTimestamp; window.capturedDataLayers.push(clone); addedFromInitial++; } catch (e) { console.error('Error cloning initial DL:', e, obj); } } }); if(addedFromInitial > 0) { console.log('Processed ' + addedFromInitial + ' initial items.'); initialItemsProcessed = true; } }
    if (initialItemsProcessed) { try { localStorage.setItem(LS_KEY, JSON.stringify(window.capturedDataLayers)); } catch (e) { console.error('Error saving initial DLs to LS:', e); } }
    window.dataLayer.push = function(...args) { const timestamp = Date.now(); let itemsPushedCount = 0; args.forEach(obj => { if (typeof obj !== 'undefined' && obj !== null) { try { const clone = JSON.parse(JSON.stringify(obj)); clone._captureTimestamp = timestamp; window.capturedDataLayers.push(clone); itemsPushedCount++; } catch (e) { console.error('Error cloning/pushing DL:', e, obj); } } });
    if (itemsPushedCount > 0) { try { localStorage.setItem(LS_KEY, JSON.stringify(window.capturedDataLayers)); } catch (e) { console.error('Error saving DLs to LS:', e); } }
    console.log('dataLayer.push intercepted. Total items:', window.capturedDataLayers.length); if (typeof originalPush === 'function') { return originalPush.apply(window.dataLayer, args); } };
    console.log('DataLayer capture script injected. Current items:', window.capturedDataLayers.length);
})();
"""


# --- Función Auxiliar VNC (Simplificada, sin parámetro host) ---
def get_vnc_url(port: int = 7900, password: str = VNC_PASSWORD) -> str:
    logger.info("Generando URL VNC apuntando a /vnc.html en localhost:%s", port)
    # Asumiendo que la mejor URL es con /vnc.html
    return f"http://localhost:{port}/vnc.html?password={password}"


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def run_selenium_validation(self, session_pk):
    """
    Tarea Celery: Crea sesión con webdriver.Remote, espera usuario y procesa.
    """
    logger.info(
        f"TASK run_selenium_validation: Iniciando para Session PK: {session_pk}"
    )
    session = None
    driver = None

    try:
        # Obtener sesión y marcar como iniciando
        with transaction.atomic():
            session = Session.objects.select_for_update().get(pk=session_pk)
            if session.status not in [Session.STATUS_PENDING, Session.STATUS_ERROR]:
                logger.warning(
                    f"Session {session_pk}: Tarea ya en progreso o finalizada (estado: {session.status}). Abortando."
                )
                return
            session.status = Session.STATUS_STARTING
            session.save(update_fields=["status", "updated_at"])
        logger.info(f"Session {session_pk}: Estado actualizado a STARTING.")

        # --- Crear y controlar sesión usando webdriver.Remote ---
        logger.info(
            f"Session {session_pk}: Creando sesión remota vía webdriver.Remote..."
        )
        command_executor_url = settings.SELENOID_URL
        if not command_executor_url:
            raise ValueError("SELENOID_URL no definido en settings.")

        options = ChromeOptions()
        options.add_argument("--window-size=1280,1024")
        # options.add_argument("--headless=new") # Descomentar si NO necesitas VNC
        # Establecer timeouts en options (preferido en Selenium 4+)
        options.timeouts = {"implicit": 0, "pageLoad": 300000, "script": 30000}  # ms

        # Crear el driver (esto inicia la sesión remota)
        driver = webdriver.Remote(
            command_executor=command_executor_url, options=options, keep_alive=True
        )
        # No es necesario set_timeouts si se hizo en Options

        selenium_session_id = driver.session_id
        logger.info(
            f"Session {session_pk}: Sesión Selenium {selenium_session_id} creada vía webdriver.Remote."
        )

        # Generar URL VNC usando la función auxiliar actualizada
        vnc_url = get_vnc_url()  # Ya no necesita host

        # Guardar datos y actualizar estado
        with transaction.atomic():
            session = Session.objects.select_for_update().get(pk=session_pk)
            session.selenium_session_id = selenium_session_id
            session.vnc_url = vnc_url
            session.status = Session.STATUS_WAITING_USER
            session.save(
                update_fields=["status", "selenium_session_id", "vnc_url", "updated_at"]
            )
        logger.info(f"Session {session_pk}: Info VNC guardada: {session.vnc_url}")
        logger.info(f"Session {session_pk}: Estado actualizado a WAITING_USER.")

        # --- Control del Navegador ---
        logger.info(f"Session {session_pk}: Navegando a {session.url}")
        driver.get(session.url)
        logger.info(f"Session {session_pk}: Navegación completada.")

        logger.info(f"Session {session_pk}: Inyectando script de captura...")
        driver.execute_script(JS_CAPTURE_DATALAYER)
        logger.info(f"Session {session_pk}: Script inyectado.")

        # --- Bucle de Espera ---
        logger.info(f"Session {session_pk}: Entrando en bucle de espera...")
        while True:
            session.refresh_from_db()
            if session.status == Session.STATUS_FINISH_REQUESTED:
                logger.info(f"Session {session_pk}: Estado FINISH_REQUESTED detectado.")
                break
            try:
                _ = driver.current_url
            except (WebDriverException, NoSuchWindowException) as wd_exc:
                logger.error(
                    f"Session {session_pk}: Navegador remoto cerrado inesperadamente: {wd_exc}",
                    exc_info=False,
                )
                raise RuntimeError(
                    "Navegador remoto cerrado inesperadamente"
                ) from wd_exc
            time.sleep(STATUS_CHECK_INTERVAL_SECONDS)

        # --- Aquí irá Paso 8: Procesamiento Final ---
        logger.info(
            f"Session {session_pk}: Bucle finalizado. Iniciando procesamiento..."
        )
        # (Código de recuperar datos, validar, reportar...)

    except (
        WebDriverException,
        TimeoutException,
        RuntimeError,
        ValueError,
    ) as exc_selenium:
        logger.error(
            f"Session {session_pk}: Error durante webdriver.Remote o control Selenium: {exc_selenium}",
            exc_info=True,
        )
        if session:
            with transaction.atomic():
                session = Session.objects.select_for_update().get(pk=session_pk)
                session.status = Session.STATUS_ERROR
                session.save(update_fields=["status", "updated_at"])

    except Exception as exc:
        logger.error(
            f"Session {session_pk}: Error GENERAL en run_selenium_validation: {exc}",
            exc_info=True,
        )
        if session:
            try:
                with transaction.atomic():
                    session_final = Session.objects.select_for_update().get(
                        pk=session_pk
                    )
                    if session_final.status not in [Session.STATUS_COMPLETED]:
                        session_final.status = Session.STATUS_ERROR
                        session_final.save(update_fields=["status", "updated_at"])
            except Session.DoesNotExist:
                logger.warning(f"Session {session_pk}: No se pudo marcar como ERROR.")
            except Exception as db_err:
                logger.error(
                    f"Session {session_pk}: Error DB al marcar ERROR: {db_err}"
                )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(f"Session {session_pk}: MaxRetries alcanzado.")
        except Exception as retry_err:
            logger.error(f"Session {session_pk}: Error en reintento: {retry_err}")

    finally:
        if driver:
            logger.info(f"Session {session_pk}: Cerrando driver Selenium en finally...")
            try:
                driver.quit()
                logger.info(f"Session {session_pk}: Driver Selenium cerrado.")
            except Exception as quit_exc:
                logger.error(
                    f"Session {session_pk}: Error cerrando driver: {quit_exc}",
                    exc_info=True,
                )
