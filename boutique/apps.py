from django.apps import AppConfig

class BoutiqueConfig(AppConfig):
    name = "boutique"

    def ready(self):
        # Importar señales para registrarlas
        import boutique.signals
