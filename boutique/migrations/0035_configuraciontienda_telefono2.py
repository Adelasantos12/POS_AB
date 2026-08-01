from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boutique', '0034_secuencia_indexes_folio_atomico'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuraciontienda',
            name='telefono2',
            field=models.CharField(blank=True, max_length=20, verbose_name='Teléfono 2'),
        ),
    ]
