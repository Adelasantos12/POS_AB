from django.db import migrations


def agregar(apps, schema_editor):
    Categoria = apps.get_model('boutique', 'Categoria')
    for nombre in ['Vestidos', 'Infantiles', 'Velos', 'Capas', 'Fajas', 'Accesorios', 'Otros']:
        if not Categoria.objects.filter(nombre__iexact=nombre).exists():
            Categoria.objects.create(nombre=nombre)


class Migration(migrations.Migration):
    dependencies = [('preparacion', '0007_correccionfabricante')]
    operations = [migrations.RunPython(agregar, migrations.RunPython.noop)]
