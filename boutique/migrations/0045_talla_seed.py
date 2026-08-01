from django.db import migrations

TALLAS_CANONICAS = [
    # (nombre, aliases, orden)
    ('XS',      ['xs', 'extra chico', 'extra-chico'],                   10),
    ('S',       ['s', 'ch', 'chico', 'small'],                          20),
    ('M',       ['m', 'med', 'mediano', 'medium'],                      30),
    ('L',       ['l', 'g', 'grande', 'large'],                          40),
    ('XL',      ['xl', 'xg', 'extra grande', 'extra-grande'],           50),
    ('2XL',     ['2xl', 'xxl', '2xg', 'doble xl'],                     60),
    ('3XL',     ['3xl', 'xxxl', '3xg'],                                 70),
    ('4XL',     ['4xl', 'xxxxl', '4xg'],                                80),
    ('U',       ['u', 'uni', 'unitalla'],                               90),
    ('2',       ['02', 'talla 2'],                                      100),
    ('4',       ['04', 'talla 4'],                                      110),
    ('6',       ['06', 'talla 6'],                                      120),
    ('8',       ['08', 'talla 8'],                                      130),
    ('10',      ['talla 10'],                                            140),
    ('12',      ['talla 12'],                                            150),
    ('14',      ['talla 14'],                                            160),
    ('16',      ['talla 16'],                                            170),
]


def seed_tallas(apps, schema_editor):
    Talla = apps.get_model('boutique', 'Talla')
    for nombre, aliases, orden in TALLAS_CANONICAS:
        Talla.objects.get_or_create(
            nombre=nombre,
            defaults={'aliases_json': aliases, 'orden': orden, 'activa': True},
        )


def borrar_tallas_seed(apps, schema_editor):
    Talla = apps.get_model('boutique', 'Talla')
    nombres = [t[0] for t in TALLAS_CANONICAS]
    Talla.objects.filter(nombre__in=nombres).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('boutique', '0044_catalogo_normalizacion'),
    ]

    operations = [
        migrations.RunPython(seed_tallas, borrar_tallas_seed),
    ]
