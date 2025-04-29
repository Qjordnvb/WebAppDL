# core/tasks.py
import logging
import json
import time
import os # Necesario para manejo de archivos/rutas
from pathlib import Path # Para manejo de rutas de archivo
from datetime import datetime # Para timestamp en resultados

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.core.files.base import ContentFile # Para guardar archivo en modelo
from django.utils import timezone # Para actualizar 'updated_at'

# Importaciones de Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService # Usar Service
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    NoSuchWindowException,
    JavascriptException, # Para errores al ejecutar JS
)

# --- Tus imports ---
from .models import Session
from .utils.validation_logic import ( # Importar funciones específicas
    filter_datalayers,
    compare_captured_with_reference,
    generate_validation_details,
    calculate_summary
)
from .utils.schema_builder import SchemaBuilder
from .utils.report_generator import ReportGenerator # Importar clase

# --- Configuración para ReportGenerator ---
# Usamos MEDIA_ROOT definido en settings.py como base para la salida temporal
# Asegúrate de que MEDIA_ROOT esté definido en settings.py
# Ejemplo: MEDIA_ROOT = BASE_DIR / 'mediafiles'
REPORT_OUTPUT_TEMP_DIR = settings.MEDIA_ROOT / 'validation_reports' / 'temp'
REPORT_CONFIG = {
    'paths': {'output': str(REPORT_OUTPUT_TEMP_DIR)}, # Convertir Path a string
    'report_formats': ['html'], # Generaremos solo HTML para guardar en el modelo
}
# Asegurar que el directorio temporal exista (worker debe tener permisos)
REPORT_OUTPUT_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Logger
logger = logging.getLogger(__name__)

# --- Constantes ---
VNC_PASSWORD = "secret"
STATUS_CHECK_INTERVAL_SECONDS = 3
# SELENIUM_COMMAND_TIMEOUT_SECONDS = 120 # Ya no se usa aquí directamente

# --- Script JavaScript (sin cambios) ---
JS_CAPTURE_DATALAYER = """
(() => {
    console.log('Attempting to inject DataLayer capture script...');
    const LS_KEY = 'capturedDataLayersLs';
    // Asegurar que window.capturedDataLayers siempre sea un array
    window.capturedDataLayers = window.capturedDataLayers || [];
    console.log('Initial capturedDataLayers length:', window.capturedDataLayers.length);

    // Cargar desde LocalStorage de forma segura
    try {
        const existingData = localStorage.getItem(LS_KEY);
        if (existingData) {
            const parsedData = JSON.parse(existingData);
            // Sobrescribir solo si lo recuperado es un array válido
            if (Array.isArray(parsedData)) {
                window.capturedDataLayers = parsedData;
                console.log('Loaded ' + parsedData.length + ' items from LocalStorage.');
            } else {
                 console.warn('Data in LocalStorage was not an array.');
            }
        }
    } catch (e) {
        console.error('Error reading or parsing LocalStorage:', e);
        // Asegurar que sigue siendo un array en caso de error
        if (!Array.isArray(window.capturedDataLayers)) {
             window.capturedDataLayers = [];
        }
    }

    // Inicializar dataLayer si no existe
    window.dataLayer = window.dataLayer || [];
    const initialTimestamp = Date.now();
    let initialItemsProcessed = false;

    // Procesar items iniciales SOLO si dataLayer es un array y tiene elementos
    if (Array.isArray(window.dataLayer) && window.dataLayer.length > 0) {
        console.log('Processing initial items in existing dataLayer (length:', window.dataLayer.length + ')');
        let addedFromInitial = 0;
        // Usar un bucle for...of o un for clásico para más control si forEach da problemas
        for (const obj of window.dataLayer) {
            // Comprobar si el objeto es procesable y no tiene ya nuestro timestamp
            if (typeof obj !== 'undefined' && obj !== null && typeof obj._captureTimestamp === 'undefined') {
                try {
                    // Clonar objeto para evitar modificar el original
                    const clone = JSON.parse(JSON.stringify(obj));
                    clone._captureTimestamp = initialTimestamp;
                    window.capturedDataLayers.push(clone);
                    addedFromInitial++;
                } catch (e) {
                    console.error('Error cloning initial DL object:', e, obj);
                    // No detener el script por un objeto mal formado
                }
            }
        }
        if (addedFromInitial > 0) {
            console.log('Processed ' + addedFromInitial + ' initial items.');
            initialItemsProcessed = true;
        }
    } else {
         console.log('window.dataLayer is not an array or is empty. Skipping initial processing.');
    }

    // Guardar en LS si se procesaron items iniciales
    if (initialItemsProcessed) {
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(window.capturedDataLayers));
        } catch (e) {
            console.error('Error saving initial DLs to LS:', e);
        }
    }

    // Guardar referencia al push original SOLO si es una función
    const originalPush = typeof window.dataLayer.push === 'function' ? window.dataLayer.push : null;

    // Sobrescribir dataLayer.push
    window.dataLayer.push = function(...args) {
        const timestamp = Date.now();
        let itemsPushedCount = 0;
        // Asegurar que window.capturedDataLayers siga siendo un array
        if (!Array.isArray(window.capturedDataLayers)) {
            console.warn('window.capturedDataLayers was not an array during push. Re-initializing.');
            window.capturedDataLayers = [];
        }

        args.forEach(obj => {
            if (typeof obj !== 'undefined' && obj !== null) {
                try {
                    const clone = JSON.parse(JSON.stringify(obj));
                    clone._captureTimestamp = timestamp;
                    window.capturedDataLayers.push(clone);
                    itemsPushedCount++;
                } catch (e) {
                    console.error('Error cloning/pushing DL object:', e, obj);
                }
            }
        });

        // Guardar en LS después de cada push exitoso
        if (itemsPushedCount > 0) {
            try {
                localStorage.setItem(LS_KEY, JSON.stringify(window.capturedDataLayers));
            } catch (e) {
                console.error('Error saving pushed DLs to LS:', e);
            }
        }

        console.log('dataLayer.push intercepted. Items pushed now:', itemsPushedCount, 'Total items:', window.capturedDataLayers.length);

        // Llamar al push original SOLO si existía y era una función
        if (originalPush) {
             // Usar try-catch por si el push original falla o tiene efectos secundarios inesperados
             try {
                return originalPush.apply(window.dataLayer, args);
             } catch(pushErr) {
                 console.error("Error calling original dataLayer.push:", pushErr);
                 // Decidir si retornar algo o no en caso de error
             }
        }
        // Si no había push original, no retornamos nada explícito (o retornamos undefined)
    };

    console.log('DataLayer capture script injected successfully. Current total items:', window.capturedDataLayers.length);
})();
"""

# --- Función Auxiliar VNC (sin cambios) ---
def get_vnc_url(port: int = 7900, password: str = VNC_PASSWORD) -> str:
    logger.info("Generando URL VNC apuntando a /vnc.html en localhost:%s", port)
    return f"http://localhost:{port}/vnc.html?password={password}"


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def run_selenium_validation(self, session_pk):
    """
    Tarea Celery: Crea sesión WebDriver, espera interacción VNC, recupera datos,
    valida, genera reporte y guarda resultados.
    """
    logger.info(
        f"TASK run_selenium_validation: Iniciando para Session PK: {session_pk}"
    )
    session = None  # Asegurar que session se define antes del try
    driver = None   # Inicializar driver a None

    try:
        # --- Obtener sesión y marcar como iniciando ---
        with transaction.atomic():
            session = Session.objects.select_for_update().get(pk=session_pk)
            if session.status not in [Session.STATUS_PENDING, Session.STATUS_ERROR]:
                logger.warning(
                    f"Session {session_pk}: Tarea no iniciada (estado: {session.status}). Abortando."
                )
                return # Salir si ya está en progreso o finalizada
            session.status = Session.STATUS_STARTING
            session.updated_at = timezone.now() # Actualizar timestamp
            session.save(update_fields=["status", "updated_at"])
        logger.info(f"Session {session_pk}: Estado actualizado a STARTING.")

        # --- Crear y controlar sesión usando webdriver.Remote ---
        logger.info(
            f"Session {session_pk}: Creando sesión remota vía webdriver.Remote..."
        )
        command_executor_url = settings.SELENOID_URL # Usa la URL del standalone-chrome ahora
        if not command_executor_url:
            # Considera usar logger.critical o similar si es un error fatal de configuración
            logger.error("SELENOID_URL (WebDriver URL) no definido en settings.")
            raise ValueError("SELENOID_URL (WebDriver URL) no definido en settings.")

        options = ChromeOptions()
        options.add_argument("--window-size=1280,1024")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        # options.add_argument("--disable-gpu") # Descomentar si hay problemas VNC
        # Establecer timeouts es buena práctica
        options.timeouts = {"implicit": 0, "pageLoad": 300000, "script": 30000} # en milisegundos

        # Inicializar driver usando webdriver.Remote
        driver = webdriver.Remote(
            command_executor=command_executor_url, options=options, keep_alive=True
        )

        selenium_session_id = driver.session_id
        logger.info(
            f"Session {session_pk}: Sesión Selenium {selenium_session_id} creada."
        )

        # Generar URL VNC
        vnc_url = get_vnc_url() # Llama a la función auxiliar definida antes

        # --- Guardar datos y actualizar estado a WAITING_USER ---
        with transaction.atomic():
            # Re-obtener por si acaso, aunque select_for_update la bloqueó antes
            session = Session.objects.select_for_update().get(pk=session_pk)
            session.selenium_session_id = selenium_session_id
            session.vnc_url = vnc_url
            session.status = Session.STATUS_WAITING_USER
            session.updated_at = timezone.now()
            session.save(
                update_fields=["status", "selenium_session_id", "vnc_url", "updated_at"]
            )
        logger.info(f"Session {session_pk}: Info VNC guardada. Estado actualizado a WAITING_USER.")

        # --- Control del Navegador: Navegar e Inyectar Script ---
        logger.info(f"Session {session_pk}: Navegando a {session.url}")
        driver.get(session.url)
        logger.info(f"Session {session_pk}: Navegación completada.")

        logger.info(f"Session {session_pk}: Inyectando script de captura...")
        # Usar la constante JS_CAPTURE_DATALAYER definida a nivel de módulo
        driver.execute_script(JS_CAPTURE_DATALAYER)
        logger.info(f"Session {session_pk}: Script inyectado.")

        # --- Bucle de Espera ---
        logger.info(f"Session {session_pk}: Entrando en bucle de espera...")
        while True:
            session.refresh_from_db() # Consultar estado actual de la BD
            if session.status == Session.STATUS_FINISH_REQUESTED:
                logger.info(f"Session {session_pk}: Estado FINISH_REQUESTED detectado.")
                break # Salir del bucle para procesar

            # Verificar si el navegador/driver sigue vivo
            try:
                _ = driver.current_url # Intenta una operación simple
            except (WebDriverException, NoSuchWindowException) as wd_exc:
                logger.error(
                    f"Session {session_pk}: Navegador remoto cerrado inesperadamente durante espera: {wd_exc}",
                    exc_info=False, # No necesitamos el traceback completo aquí generalmente
                )
                # Marcar como error y propagar para salir y limpiar
                try: # Anidar try para asegurar que el fallo de DB no oculte el error original
                    with transaction.atomic():
                        session_err = Session.objects.select_for_update().get(pk=session_pk)
                        session_err.status = Session.STATUS_ERROR
                        session_err.updated_at = timezone.now()
                        # Guardar mensaje de error si tienes un campo para ello
                        # session_err.error_message = "Navegador remoto cerrado inesperadamente"
                        session_err.save(update_fields=["status", "updated_at"]) # Añadir error_message si existe
                except Exception as db_sub_err:
                    logger.error(f"Session {session_pk}: Error DB al intentar marcar ERROR por cierre inesperado: {db_sub_err}")
                # Propagar el error original para que el try/except exterior lo maneje
                raise RuntimeError("Navegador remoto cerrado inesperadamente") from wd_exc

            # Esperar antes de volver a checkear el estado en la BD
            time.sleep(STATUS_CHECK_INTERVAL_SECONDS)

        # --- INICIO: PASO 8 - Lógica de Procesamiento ---
        logger.info(f"Session {session_pk}: Bucle finalizado. Iniciando procesamiento final...")

        # 8.1. Actualizar estado a Procesando
        with transaction.atomic():
            session = Session.objects.select_for_update().get(pk=session_pk)
            session.status = Session.STATUS_PROCESSING
            session.updated_at = timezone.now()
            session.save(update_fields=["status", "updated_at"])
        logger.info(f"Session {session_pk}: Estado actualizado a PROCESSING.")

        # 8.2. Recuperar datos del navegador
        captured_data_raw = []
        try:
            # Esperar un instante muy breve por si acaso algún evento final tarda en registrarse
            time.sleep(0.5)
            captured_data_raw = driver.execute_script("return window.capturedDataLayers;")
            # Validar que sea una lista (puede ser null o undefined si hubo error JS)
            if captured_data_raw is None or not isinstance(captured_data_raw, list):
                 logger.warning(f"Session {session_pk}: window.capturedDataLayers devolvió {type(captured_data_raw)}. Se tratará como lista vacía.")
                 captured_data_raw = []
            logger.info(f"Session {session_pk}: Datos recuperados del navegador ({len(captured_data_raw)} items).")

        except JavascriptException as js_exc:
            logger.error(f"Session {session_pk}: Error ejecutando script JS para recuperar datos: {js_exc}")
            # Considerar esto un error de sesión, ya que no tenemos los datos
            raise RuntimeError("Fallo crítico al recuperar datos del navegador vía JS") from js_exc
        except WebDriverException as wd_get_exc:
             logger.error(f"Session {session_pk}: Error de WebDriver al intentar recuperar datos: {wd_get_exc}")
             raise RuntimeError("Fallo de WebDriver al recuperar datos") from wd_get_exc

        # --- 8.2b Usar SchemaBuilder ---
        logger.info(f"Session {session_pk}: Construyendo schema estructurado desde la referencia...")
        structured_schema = None # Inicializar
        # Verificar que la entrada guardada sea una lista, como se espera ahora
        if not isinstance(session.reference_schema, list):
            logger.error(f"Session {session_pk}: El JSON de referencia guardado no es una lista (tipo: {type(session.reference_schema)}). No se puede construir el schema.")
            raise ValueError("El JSON de referencia proporcionado no es una lista válida.")

        try:
            # Crear el schema estructurado usando SchemaBuilder
            builder = SchemaBuilder(reference_datalayers=session.reference_schema)
            structured_schema = builder.build_schema() # Este debería ser el diccionario esperado

            # Verificar que el builder funcionó y devolvió un diccionario
            if not structured_schema or not isinstance(structured_schema, dict):
                 logger.error(f"SchemaBuilder no generó un diccionario válido. Resultado: {structured_schema}")
                 raise RuntimeError("SchemaBuilder no pudo generar un schema estructurado válido.")
            logger.info(f"Session {session_pk}: Schema estructurado construido exitosamente.")

        except Exception as build_exc:
             logger.exception(f"Session {session_pk}: Error durante la construcción del schema con SchemaBuilder: {build_exc}")
             raise RuntimeError("Error construyendo el schema de validación") from build_exc
        # --- Fin Uso SchemaBuilder ---


        # 8.3. Procesar Datos y Validar (Usando el schema ESTRUCTURADO)
        logger.info(f"Session {session_pk}: Iniciando validación lógica con schema construido...")
        final_validation_results = {} # Inicializar
        try:
            # AHORA pasamos structured_schema a las funciones de validación
            # Nota: Ajusta si tus funciones devuelven/necesitan algo diferente
            validation_details = generate_validation_details(captured_data_raw, structured_schema)
            comparison_results = compare_captured_with_reference(validation_details, structured_schema)
            summary_results = calculate_summary(validation_details, comparison_results)

            # Combinar resultados en un solo JSON para guardar
            final_validation_results = {
                "summary": summary_results,
                "comparison": comparison_results,
                "details": validation_details,
                "processing_timestamp": timezone.now().isoformat(),
                "validated_url": session.url,
                # "is_overall_valid": summary_results.get('is_valid', False) # Opcional
            }
            logger.info(f"Session {session_pk}: Validación lógica completada.")

        except Exception as val_exc:
            logger.exception(f"Session {session_pk}: Error durante la ejecución de validation_logic: {val_exc}")
            raise RuntimeError("Error durante el proceso de validación de datos") from val_exc

        # 8.4. Generar Reporte HTML
        logger.info(f"Session {session_pk}: Generando reporte HTML...")
        report_filepath_temp = None # Para asegurar limpieza en caso de error
        try:
            report_generator = ReportGenerator(config=REPORT_CONFIG)
            report_filepath_temp = report_generator.generate_html_report(
                validation_results=final_validation_results,
                url=session.url,
                schema=structured_schema # Pasar el schema construido
            )

            if not report_filepath_temp or "(ERROR)" in report_filepath_temp:
                raise RuntimeError(f"Fallo al generar el reporte HTML: {report_filepath_temp}")

            logger.info(f"Session {session_pk}: Reporte HTML generado temporalmente en {report_filepath_temp}.")

            # 8.5. Guardar Resultados y Reporte en el Modelo Session
            logger.info(f"Session {session_pk}: Guardando resultados y reporte en la base de datos...")
            with transaction.atomic():
                session_to_save = Session.objects.select_for_update().get(pk=session_pk)
                session_to_save.captured_data = captured_data_raw
                session_to_save.validation_results = final_validation_results

                report_filename = Path(report_filepath_temp).name
                try:
                    with open(report_filepath_temp, 'rb') as f_report:
                        # Usar save=False y luego guardar el modelo una sola vez
                        session_to_save.report_file.save(report_filename, ContentFile(f_report.read()), save=False)
                    logger.info(f"Session {session_pk}: Contenido del reporte preparado para guardar como {report_filename}.")
                except Exception as file_err:
                     logger.error(f"Session {session_pk}: Error leyendo o preparando archivo de reporte para modelo: {file_err}", exc_info=True)
                     raise RuntimeError("Fallo al leer/preparar el archivo de reporte") from file_err

                session_to_save.status = Session.STATUS_COMPLETED # Marcar como completada
                session_to_save.updated_at = timezone.now()
                # Guardar todos los campos actualizados
                session_to_save.save(update_fields=['captured_data', 'validation_results', 'report_file', 'status', 'updated_at'])

            logger.info(f"Session {session_pk}: Resultados y reporte guardados. Estado actualizado a COMPLETED.")

        except Exception as report_save_exc:
             logger.exception(f"Session {session_pk}: Error generando o guardando reporte/resultados: {report_save_exc}")
             raise RuntimeError("Fallo procesando/guardando resultados o reporte") from report_save_exc
        finally:
            # Limpiar archivo temporal si existe
            if report_filepath_temp and os.path.exists(str(report_filepath_temp)): # os.path.exists necesita string
                 try:
                      os.remove(str(report_filepath_temp))
                      logger.debug(f"Archivo temporal {report_filepath_temp} eliminado.")
                 except OSError as rm_err:
                      logger.warning(f"No se pudo eliminar el archivo temporal {report_filepath_temp}: {rm_err}")
        # --- FIN: PASO 8 ---

    # --- Bloque except principal para errores durante el procesamiento ---
    except (WebDriverException, TimeoutException, RuntimeError, ValueError, JavascriptException, AttributeError) as processing_exc:
        logger.error(f"Session {session_pk}: Error durante ejecución de tarea o procesamiento: {processing_exc}", exc_info=True)
        try:
            with transaction.atomic():
                # Actualizar estado a ERROR solo si no está ya COMPLETED o ERROR
                updated_count = Session.objects.filter(pk=session_pk) \
                                     .exclude(status__in=[Session.STATUS_COMPLETED, Session.STATUS_ERROR]) \
                                     .update(status=Session.STATUS_ERROR, updated_at=timezone.now())
                if updated_count > 0:
                    logger.info(f"Session {session_pk}: Estado actualizado a ERROR debido a excepción.")
                else:
                    logger.info(f"Session {session_pk}: Estado no actualizado a ERROR (ya era COMPLETED o ERROR).")
        except Exception as db_err_on_err:
             logger.error(f"Session {session_pk}: Error DB al intentar marcar ERROR final: {db_err_on_err}")
        # No reintentamos errores de lógica/procesamiento automáticamente aquí

    # --- Bloque except para errores muy generales/inesperados ---
    except Exception as exc:
        logger.error(f"Session {session_pk}: Error GENERAL INESPERADO en run_selenium_validation: {exc}", exc_info=True)
        # Marcar como ERROR (con la lógica mejorada)
        try:
             with transaction.atomic():
                 updated_count = Session.objects.filter(pk=session_pk) \
                                     .exclude(status__in=[Session.STATUS_COMPLETED, Session.STATUS_ERROR]) \
                                     .update(status=Session.STATUS_ERROR, updated_at=timezone.now())
                 if updated_count > 0:
                     logger.info(f"Session {session_pk}: Estado actualizado a ERROR debido a excepción general.")
                 else:
                    logger.info(f"Session {session_pk}: Estado no actualizado a ERROR (ya era COMPLETED o ERROR).")
        except Exception as db_err:
             logger.error(f"Session {session_pk}: Error DB al marcar ERROR general: {db_err}")

        # Considerar reintentar para errores genéricos (podría ser fallo temporal de red, etc.)
        try:
            # bind=True en @shared_task nos da 'self' para llamar a retry
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(f"Session {session_pk}: MaxRetries alcanzado para error general.")
        except Exception as retry_err: # Otros errores durante el reintento
            logger.error(f"Session {session_pk}: Error durante el reintento: {retry_err}")

    # --- Bloque Finally para asegurar limpieza ---
    finally:
        # Cerrar el driver de Selenium si se llegó a crear
        if driver:
            logger.info(f"Session {session_pk}: Cerrando driver Selenium en finally...")
            try:
                driver.quit()
                logger.info(f"Session {session_pk}: Driver Selenium cerrado.")
            except Exception as quit_exc:
                # Loggear error al cerrar, pero no relanzar para no ocultar error original si hubo uno
                logger.error(
                    f"Session {session_pk}: Error cerrando driver en finally: {quit_exc}",
                    exc_info=False, # Podríamos poner True si queremos el traceback completo
                )
