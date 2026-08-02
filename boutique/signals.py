from django.db.models.signals import post_migrate
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)

@receiver(post_migrate)
def populate_catalogs_handler(sender, **kwargs):
    """
    Handler para poblar catálogos automáticamente después de las migraciones.
    Usa imports locales para evitar problemas de carga circular.
    """
    # Solo ejecutar para nuestra app
    if sender.name != 'boutique':
        return

    import os
    if os.environ.get('RUN_MAIN') == 'true':
        # Evitar ejecución doble en dev con autoreload
        return

    from django.core.management import call_command
    try:
        logger.info("Poblando catálogos base desde post_migrate...")
        call_command('populate_catalogs')
        call_command('setup_roles_v2')
    except Exception as e:
        logger.error(f"Error poblando catálogos en post_migrate: {e}")
