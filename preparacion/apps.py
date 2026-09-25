from django.apps import AppConfig


class PreparacionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'preparacion'
    verbose_name = 'Preparación del inventario inicial'

    def ready(self):
        from . import signals  # noqa: F401
