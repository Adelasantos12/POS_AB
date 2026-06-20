from django.core.management.base import BaseCommand
from boutique.models import Color, Tela, Categoria, ConfiguracionTienda

class Command(BaseCommand):
    help = 'Puebla los catálogos base de colores y telas'

    def handle(self, *args, **options):
        # ── Configuración de la Tienda (solo rellena campos vacíos) ──────────
        config = ConfiguracionTienda.get_solo()
        updated = False
        defaults = {
            'nombre_comercial': 'Adelé Boutique Matriz',
            'direccion': 'Juan Álvarez 1596, Guadalajara',
            'telefono_whatsapp': '3315319121',
            'telefono2': '3316812938',
            'horarios': 'Lun-Vie 12:00–19:00  |  Sáb 11:00–16:00',
            'prefijo_sucursal': 'ADELE',
            'politica_cambios': (
                'No se aceptan cambios ni devoluciones.\n'
                'Presenta este ticket al recoger tu pedido.\n'
                'El plazo de entrega es estimado y puede variar.'
            ),
            'politica_apartados': (
                'El apartado no es reembolsable.\n'
                'El producto se reserva por 30 días naturales.\n'
                'Presenta este ticket al recoger tu pedido.'
            ),
        }
        for field, value in defaults.items():
            if not getattr(config, field, ''):
                setattr(config, field, value)
                updated = True
        if updated:
            config.save()

        # Colores
        colores_base = [
            ('Sin definir', '#CCCCCC', 'N/A'),
            ('Blanco', '#FFFFFF', 'Neutro'),
            ('Negro', '#000000', 'Neutro'),
            ('Rosa Palo', '#E8B4B8', 'Rosa'),
            ('Rosa Mauve', '#673147', 'Rosa'),
            ('Azul Marino', '#000080', 'Azul'),
            ('Azul Cielo', '#87CEEB', 'Azul'),
            ('Rojo Coral', '#FF7F50', 'Rojo'),
            ('Verde Esmeralda', '#50C878', 'Verde'),
            ('Champagne', '#F7E7CE', 'Tierra'),
            ('Nude', '#E3BC9A', 'Tierra'),
            ('Borgonia', '#800020', 'Rojo'),
            ('Lavanda', '#E6E6FA', 'Morado'),
        ]

        for nombre, hex_code, familia in colores_base:
            Color.objects.get_or_create(
                nombre=nombre,
                defaults={'codigo_hex': hex_code, 'familia': familia, 'es_predefinido': True}
            )

        # Telas
        telas_base = [
            ('Satín', 'Tela suave con brillo'),
            ('Encaje', 'Tejido ornamental y transparente'),
            ('Chiffón', 'Tela ligera y vaporosa'),
            ('Tul', 'Tejido ligero en forma de malla'),
            ('Mikado', 'Seda natural gruesa con brillo'),
            ('Crepé', 'Tela de superficie granular y arrugada'),
            ('Organza', 'Tejido de seda o algodón transparente y rígido'),
        ]

        for nombre, desc in telas_base:
            Tela.objects.get_or_create(
                nombre=nombre,
                defaults={'descripcion': desc, 'es_predefinida': True}
            )

        # Categorías
        categorias = [
            'Sin definir', 'Novias', 'Damas', 'Accesorios', 'Servicios',
            'Vestido Novia', 'Vestido Dama', 'Velo', 'Tocado', 'Ajuste'
        ]
        for cat in categorias:
            Categoria.objects.get_or_create(nombre=cat)

        self.stdout.write(self.style.SUCCESS('Catálogos base poblados correctamente'))
