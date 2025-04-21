# webappdl/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
# Importamos la función específica para servir estáticos en desarrollo
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
# Ya no necesitamos 'static' de django.conf.urls.static a menos que sirvas MEDIA files

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')), # Incluye las URLs de tu app 'core'
]

# Servir archivos estáticos durante el desarrollo usando staticfiles_urlpatterns
# Esto utiliza los STATICFILES_FINDERS configurados en settings.py
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    # NOTA: Si en el futuro necesitas servir MEDIA_URL (archivos subidos),
    # SÍ necesitarías importar 'static' y añadir esa línea por separado:
    # from django.conf.urls.static import static
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
