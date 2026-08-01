from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boutique', '0033_modelo_ampliado_servicios_tracking'),
    ]

    operations = [
        # 1. Secuencia model for atomic folio generation
        migrations.CreateModel(
            name='Secuencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prefijo', models.CharField(max_length=20)),
                ('fecha', models.DateField()),
                ('ultimo_numero', models.PositiveIntegerField(default=0)),
            ],
            options={
                'unique_together': {('prefijo', 'fecha')},
            },
        ),

        # 2. DB indexes on Pedido
        migrations.AddIndex(
            model_name='pedido',
            index=models.Index(fields=['estado'], name='pedido_estado_idx'),
        ),
        migrations.AddIndex(
            model_name='pedido',
            index=models.Index(fields=['fecha_entrega_estimada'], name='pedido_entrega_idx'),
        ),
        migrations.AddIndex(
            model_name='pedido',
            index=models.Index(fields=['estado', 'fecha_entrega_estimada'], name='pedido_estado_entrega_idx'),
        ),

        # 3. DB indexes on MovimientoCaja
        migrations.AddIndex(
            model_name='movimientocaja',
            index=models.Index(fields=['fecha'], name='movcaja_fecha_idx'),
        ),
        migrations.AddIndex(
            model_name='movimientocaja',
            index=models.Index(fields=['caja', 'fecha'], name='movcaja_caja_fecha_idx'),
        ),
    ]
