from django.core.management.base import BaseCommand
from boutique.models import Color, Tela, Categoria, ConfiguracionTienda, Modelo


class Command(BaseCommand):
    help = 'Puebla los catálogos base de colores, telas y categorías'

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

        # ── Colores ────────────────────────────────────────────────────────────
        # (nombre, hex, familia)  — nombres que cualquier vendedora entiende de inmediato
        colores_base = [
            # Neutros / Metálicos
            ('Sin definir',  '#CCCCCC', 'N/A'),
            ('Blanco',       '#FFFFFF', 'Neutro'),
            ('Marfil',       '#FFFFF0', 'Neutro'),   # blanco con toque cálido, muy común en novias
            ('Champagne',    '#F7E7CE', 'Neutro'),
            ('Nude',         '#E3BC9A', 'Neutro'),
            ('Plata',        '#C0C0C0', 'Neutro'),
            ('Dorado',       '#D4AF37', 'Neutro'),
            ('Gris',         '#808080', 'Neutro'),
            ('Negro',        '#000000', 'Neutro'),

            # Rosas
            ('Rosa Bebé',     '#FFB6C1', 'Rosa'),   # pink muy suave
            ('Rosa',          '#FF69B4', 'Rosa'),   # rosa estándar
            ('Rosa Palo',     '#E8B4B8', 'Rosa'),   # polvoso / dusty rose
            ('Durazno',       '#FFCBA4', 'Rosa'),   # peach — muy solicitado en XV
            ('Coral',         '#FF7F50', 'Rosa'),
            ('Rosa Mexicano', '#E91E8C', 'Rosa'),   # hot pink / mexicano intenso
            ('Fucsia',        '#FF007F', 'Rosa'),

            # Rojos
            ('Rojo',          '#CC0000', 'Rojo'),
            ('Coral Rojo',    '#E05C48', 'Rojo'),
            ('Guinda',        '#6D0716', 'Rojo'),   # muy popular en México
            ('Vino',          '#722F37', 'Rojo'),   # burgundy / borgoña

            # Azules
            ('Cielo',         '#87CEEB', 'Azul'),   # celeste suave
            ('Aqua',          '#7FFFD4', 'Azul'),   # aqua / turquesa claro — favorito XV
            ('Turquesa',      '#40E0D0', 'Azul'),
            ('Azul Rey',      '#4169E1', 'Azul'),
            ('Azul Marino',   '#000080', 'Azul'),
            ('Azul Pavo Real','#005F73', 'Azul'),   # peacock — muy elegante

            # Verdes
            ('Verde Menta',   '#98FF98', 'Verde'),
            ('Verde Esmeralda','#50C878', 'Verde'),
            ('Verde Militar', '#4B5320', 'Verde'),

            # Morados
            ('Lila',          '#C8A2C8', 'Morado'),  # suave, para damas
            ('Lavanda',       '#E6E6FA', 'Morado'),
            ('Morado',        '#800080', 'Morado'),
            ('Uva',           '#6F2DA8', 'Morado'),  # deep purple

            # Tierra / Cafés
            ('Canela',        '#D2691E', 'Tierra'),
            ('Camel',         '#C19A6B', 'Tierra'),
            ('Café',          '#6F4E37', 'Tierra'),
            ('Terracota',     '#E2725B', 'Tierra'),

            # Especiales
            ('Multicolor',    '#FF69B4', 'Especial'),
            ('Estampado',     '#888888', 'Especial'),
        ]

        for nombre, hex_code, familia in colores_base:
            Color.objects.get_or_create(
                nombre=nombre,
                defaults={'codigo_hex': hex_code, 'familia': familia, 'es_predefinido': True}
            )

        # ── Telas ──────────────────────────────────────────────────────────────
        # (nombre, descripción breve que ayuda a identificar al tacto/vista)
        telas_base = [
            # Las 7 originales
            ('Satín',        'Brillante y suave al tacto — la más común en vestidos de novia'),
            ('Encaje',       'Tejido ornamental transparente — detalles y sobrecapas'),
            ('Chiffón',      'Ligera, vaporosa y translúcida — fluye con el movimiento'),
            ('Tul',          'Malla muy fina y rígida — faldas con volumen y velos'),
            ('Mikado',       'Seda gruesa con brillo mate — estructura sin armazón'),
            ('Crepé',        'Superficie granulada, caída limpia — muy elegante y moderno'),
            ('Organza',      'Transparente y rígida — capas y detalles estructurados'),

            # Nuevas
            ('Bordado',      'Tela con diseños cosidos en hilo — relieves florales o geométricos'),
            ('Glasé',        'Tela con superficie brillante a base de acetato o poliéster'),
            ('Jacquard',     'Tejido con diseño incorporado en la tela — brocados y relieves'),
            ('Terciopelo',   'Pelo corto y suave — profundidad de color, elegante en invierno'),
            ('Lentejuela',   'Tela cubierta de brillos/lentejuelas — fiestas y quinceañeras'),
            ('Brocado',      'Tela gruesa con diseños en relieve dorados o plateados'),
            ('Tafetán',      'Tela crujiente con brillo — holds su forma, buena para volumen'),
            ('Raso',         'Similar al satín pero más opaco y con caída más pesada'),
            ('Gasa',         'Muy ligera y translúcida — capas sobrepuestas y mangas'),
            ('Strech',       'Tela elástica — entallada al cuerpo, cómoda para sirenas'),
            ('Seda Natural', 'Fibra natural — máxima suavidad y brillo natural'),
        ]

        for nombre, desc in telas_base:
            Tela.objects.get_or_create(
                nombre=nombre,
                defaults={'descripcion': desc, 'es_predefinida': True}
            )

        # ── Categorías ─────────────────────────────────────────────────────────
        categorias_correctas = [
            'Sin definir',
            'Novias',
            'Damas',
            'Meninas',       # niñas de 0-12 años
            'Quinceañera',
            'Fiesta',        # vestidos de gala/cóctel para invitadas
            'Importado',     # vestidos de proveedores extranjeros
            'Accesorios',
            'Velo',
            'Tocado',
            'Servicios',
            'Ajuste',
        ]
        for cat in categorias_correctas:
            Categoria.objects.get_or_create(nombre=cat)

        # Limpiar duplicados históricos → reasignar productos
        from boutique.models import Producto
        for nombre_viejo, nombre_nuevo in [
            ('Vestido Novia', 'Novias'),
            ('Vestido Dama',  'Damas'),
            ('Vestido Damas', 'Damas'),
        ]:
            try:
                vieja = Categoria.objects.get(nombre=nombre_viejo)
                nueva, _ = Categoria.objects.get_or_create(nombre=nombre_nuevo)
                Producto.objects.filter(categoria=vieja).update(categoria=nueva)
                vieja.delete()
            except Categoria.DoesNotExist:
                pass

        # ── Modelos de vestido ─────────────────────────────────────────────────
        # Siluetas y cortes usados en boutiques de Guadalajara
        modelos_base = [
            ('Sirena',      'Se ajusta al cuerpo hasta la rodilla y se abre hacia abajo — resalta curvas'),
            ('Evasé',       'Corte A desde la cintura — favorece casi todas las figuras'),
            ('Princesa',    'Falda amplia con mucho volumen desde la cintura — estilo clásico'),
            ('Crinolina',   'Falda muy esponjada con armazón interior — muy solicitada en XV'),
            ('Corte Recto', 'Cae recto desde los hombros — moderno y minimalista'),
            ('Con Cola',    'Vestido con extensión en la parte trasera — catedral, capilla o barrida'),
            ('Globo',       'Falda inflada en la parte baja — tendencia para quinceañeras'),
            ('Corto',       'Vestido por encima de la rodilla — para damas, fiesta o cóctel'),
            ('Dos Piezas',  'Top y falda separados — muy versátil para arreglos posteriores'),
            ('Asimétrico',  'Ruedo irregular o un hombro — diseños modernos y originales'),
        ]
        for nombre, desc in modelos_base:
            Modelo.objects.get_or_create(
                nombre=nombre,
                defaults={'descripcion': desc}
            )

        self.stdout.write(self.style.SUCCESS('Catálogos base poblados correctamente'))
