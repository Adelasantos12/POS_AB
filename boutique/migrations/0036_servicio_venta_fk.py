import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boutique', '0035_configuraciontienda_telefono2'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicio',
            name='venta',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='servicios_incluidos',
                to='boutique.venta',
            ),
        ),
    ]
