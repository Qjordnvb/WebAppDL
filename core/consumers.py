# core/consumers.py

import json
import asyncio
import logging
import os
from pathlib import Path
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .controllers.browser_controller import BrowserController

logger = logging.getLogger(__name__)

class SessionConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.session_group_name = f'session_{self.session_id}'
        self.session_obj = None
        self.browser_controller = None

        logger.info(f"WS: Intentando conectar sesión: {self.session_id}")
        self.session_obj = await self.get_session_db(self.session_id)

        if self.session_obj:
            await self.channel_layer.group_add(self.session_group_name, self.channel_name)
            await self.accept()
            logger.info(f"WS: Conexión aceptada para sesión: {self.session_id}.")
        else:
            logger.error(f"WS: Sesión {self.session_id} no encontrada. Rechazando conexión.")
            await self.close()

    async def disconnect(self, close_code):
        logger.info(f"WS: Desconectando sesión {self.session_id}, código: {close_code}")
        if self.browser_controller:
            await self.browser_controller.stop()
            self.browser_controller = None
            logger.info(f"WS: Controlador de navegador detenido para sesión {self.session_id}")
        await self.channel_layer.group_discard(self.session_group_name, self.channel_name)

    async def receive(self, text_data):
        logger.debug(f"WS: Mensaje recibido sesión {self.session_id}: {text_data[:100]}...")
        try:
            data = json.loads(text_data)
            action = data.get('action')
            if action == "init_browser":
                await self.handle_init_browser(data)
            else:
                logger.warning(f"WS: Acción desconocida recibida: {action}")
                await self.send_error("Acción desconocida.")
        except json.JSONDecodeError:
            logger.error("WS: Error decodificando JSON")
            await self.send_error("Mensaje JSON inválido.")
        except Exception as e:
            logger.exception(f"WS: Error procesando mensaje: {e}")
            await self.send_error(f"Error interno: {e}")

    async def handle_init_browser(self, data):
        if not os.environ.get('SELENOID_URL'):
            logger.critical("Configuración Incompleta: SELENOID_URL no definida.")
            await self.send_error("Error de configuración del servidor (Moon Base URL).")
            return
        if not self.session_obj:
            logger.error("WS: Intento de inicializar navegador sin sesión válida.")
            await self.send_error("Sesión no válida.")
            return
        if self.browser_controller and self.browser_controller._state != "stopped":
            logger.warning(f"WS: El navegador ya está activo o iniciándose (estado: {self.browser_controller._state}).")
            return
        logger.info(f"WS: Inicializando BrowserController para sesión {self.session_id}...")
        self.browser_controller = BrowserController(session_id=self.session_id,session_url=self.session_obj.url,notify_callback=self.notify_client)
        url_to_navigate = getattr(self.session_obj, 'url', None)
        if url_to_navigate:
            asyncio.create_task(self.browser_controller.start_and_navigate(url_to_navigate))
            logger.info(f"WS: Tarea de inicio y navegación para {url_to_navigate} creada.")
        else:
            logger.error(f"WS: El objeto Session (ID: {self.session_id}) no tiene atributo 'url'.")
            await self.send_error("Error interno: falta URL de sesión.")
            self.browser_controller = None

    async def notify_client(self, action, data):
        logger.debug(f"WS: Recibido del Controller: action={action}, data={str(data)[:200]}...")
        if action == "datalayer_push":
            await self.send_message("new_datalayer", {"payload": data})
        elif action == "browser_ready":
            logger.info(
                f"Notificando browser_ready con VNC URL: {data.get('vnc_info')}"
            )
            payload = {
                "session_id": self.session_id,
                "vnc_info": data.get("vnc_info"),
                "cdp_url": data.get("cdp_url"),
            }
            await self.send_message("browser_ready", payload)
        elif action in ["browser_state", "navigation_complete", "navigation_error", "error"]:
            await self.send_message(action, data)
        else:
            logger.warning(f"WS: Acción desconocida o no manejada recibida del controller: {action}")

    async def send_message(self, action, data=None):
        if data is None: data = {}
        payload = {'action': action, **data}
        log_payload_str = json.dumps(payload)
        if len(log_payload_str) > 500:
            log_payload_str = log_payload_str[:500] + "...(truncated)"
        logger.debug(f"WS: Enviando al cliente: {log_payload_str}")
        try:
            await self.send(text_data=json.dumps(payload))
        except Exception as e:
            logger.exception(f"WS: Error enviando mensaje {action}: {e}")

    async def send_error(self, message):
        await self.send_message("error", {"message": message})

    @database_sync_to_async
    def _get_session_db_sync(self, session_id):
        from .models import Session
        try:
            return Session.objects.get(id=session_id)
        except Session.DoesNotExist:
            logger.warning(f"DB: Sesión {session_id} no encontrada en _get_session_db_sync.")
            return None
        except Exception as e:
            logger.exception(f"DB: Error al obtener sesión {session_id}: {e}")
            return None

    async def get_session_db(self, session_id):
        return await self._get_session_db_sync(session_id)
