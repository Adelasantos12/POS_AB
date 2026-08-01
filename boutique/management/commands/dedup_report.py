"""
Reporte de duplicados en catálogos ANTES de aplicar la restricción de unicidad.

Uso:
    python manage.py dedup_report
    python manage.py dedup_report --fix      # marca duplicados en pantalla (NO los elimina)
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from boutique.models import Producto, Color, Tela, Modelo, Categoria, Talla
from boutique.utils import normalizar_nombre, nombres_son_iguales


class Command(BaseCommand):
    help = 'Detecta duplicados en catálogos y variantes de productos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Muestra acciones sugeridas (no aplica cambios automáticos)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('═' * 70))
        self.stdout.write(self.style.SUCCESS('  REPORTE DE DUPLICADOS — Adelé Boutique'))
        self.stdout.write(self.style.SUCCESS('═' * 70))

        self._check_catalog_names('Color', Color.objects.all())
        self._check_catalog_names('Tela', Tela.objects.all())
        self._check_catalog_names('Modelo', Modelo.objects.all())
        self._check_catalog_names('Categoria', Categoria.objects.all())
        self._check_producto_variantes()
        self._check_talla_cobertura()

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Reporte completado. Ningún dato fue modificado.'))

    def _check_catalog_names(self, label, qs):
        self.stdout.write(f'\n── {label} ─────────────────────────────')
        grupos = {}
        for obj in qs:
            key = normalizar_nombre(obj.nombre).lower()
            grupos.setdefault(key, []).append(obj)

        dupes = {k: v for k, v in grupos.items() if len(v) > 1}
        if not dupes:
            self.stdout.write(self.style.SUCCESS(f'  ✓ Sin duplicados ({qs.count()} registros)'))
            return

        for key, objs in dupes.items():
            ids = ', '.join(f'#{o.pk} "{o.nombre}"' for o in objs)
            self.stdout.write(
                self.style.WARNING(f'  ⚠ Duplicado normalizado "{key}": {ids}')
            )

    def _check_producto_variantes(self):
        self.stdout.write('\n── Variantes de Producto (unicidad modelo+color+tela+talla_obj) ───')

        # Solo considerar productos con modelo y talla_obj asignados
        qs = (
            Producto.objects
            .filter(modelo__isnull=False, talla_obj__isnull=False)
            .values('modelo_id', 'color_id', 'tela_id', 'talla_obj_id')
            .annotate(cnt=Count('id'))
            .filter(cnt__gt=1)
        )
        if not qs.exists():
            self.stdout.write(self.style.SUCCESS('  ✓ Sin variantes duplicadas con FK completas'))
        else:
            for row in qs:
                self.stdout.write(
                    self.style.WARNING(
                        f'  ⚠ {row["cnt"]} productos con '
                        f'modelo={row["modelo_id"]} color={row["color_id"]} '
                        f'tela={row["tela_id"]} talla_obj={row["talla_obj_id"]}'
                    )
                )

        # Also report products where modelo is set but talla_obj is NULL (not yet migrated)
        sin_talla_obj = Producto.objects.filter(modelo__isnull=False, talla_obj__isnull=True).count()
        if sin_talla_obj:
            self.stdout.write(
                self.style.WARNING(
                    f'  ℹ {sin_talla_obj} producto(s) tienen modelo pero talla_obj=NULL '
                    f'(no participan en la restricción de unicidad todavía)'
                )
            )

    def _check_talla_cobertura(self):
        self.stdout.write('\n── Cobertura de Talla en Productos ───────────────────────────────')
        total = Producto.objects.count()
        con_obj = Producto.objects.filter(talla_obj__isnull=False).count()
        self.stdout.write(f'  Productos con talla_obj: {con_obj}/{total}')

        # Find raw talla values not in catalog
        tallas_catalogadas = set(Talla.objects.values_list('nombre', flat=True))
        tallas_raw = set(
            Producto.objects.filter(talla_obj__isnull=True)
            .values_list('talla', flat=True)
            .distinct()
        )
        sin_match = tallas_raw - tallas_catalogadas
        if sin_match:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠ Valores de talla sin equivalente en catálogo: {sorted(sin_match)}'
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ Todos los valores de talla tienen equivalente en catálogo'))
