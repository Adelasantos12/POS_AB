from django.db import migrations


def fix_categorias(apps, schema_editor):
    Categoria = apps.get_model('boutique', 'Categoria')
    Producto = apps.get_model('boutique', 'Producto')

    # Merge duplicates: re-asignar productos y eliminar la categoría redundante
    merges = [
        ('Vestido Novia', 'Novias'),
        ('Vestido Dama',  'Damas'),
        ('Vestido Damas', 'Damas'),   # por si existe con 's'
        ('Quinceañera',   'Quinceañera'),  # normalizar acento si existe sin él
    ]
    for nombre_viejo, nombre_nuevo in merges:
        try:
            vieja = Categoria.objects.get(nombre=nombre_viejo)
        except Categoria.DoesNotExist:
            continue
        nueva, _ = Categoria.objects.get_or_create(nombre=nombre_nuevo)
        Producto.objects.filter(categoria=vieja).update(categoria=nueva)
        vieja.delete()

    # Agregar categorías nuevas
    nuevas = ['Meninas', 'Fiesta', 'Importado', 'Quinceañera']
    for nombre in nuevas:
        Categoria.objects.get_or_create(nombre=nombre)


class Migration(migrations.Migration):

    dependencies = [
        ('boutique', '0037_auto_0037'),
    ]

    operations = [
        migrations.RunPython(fix_categorias, migrations.RunPython.noop),
    ]
