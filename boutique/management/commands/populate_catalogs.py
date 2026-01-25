from django.core.management.base import BaseCommand
from boutique.models import Color, Tela, Categoria

class Command(BaseCommand):
    help = 'Puebla los catálogos base de colores y telas'

    def handle(self, *args, **options):
        # Colores
        colores_base = [
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
        categorias = ['Vestido Novia', 'Vestido Dama', 'Velo', 'Tocado', 'Accesorio', 'Ajuste']
        for cat in categorias:
            Categoria.objects.get_or_create(nombre=cat)

        self.stdout.write(self.style.SUCCESS('Catálogos base poblados correctamente'))
