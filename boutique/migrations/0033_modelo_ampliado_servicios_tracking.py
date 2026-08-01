from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("boutique", "0032_idempotencylog_alter_producto_unique_together_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. ConfiguracionTienda.horarios
        migrations.AddField(
            model_name="configuraciontienda",
            name="horarios",
            field=models.TextField(blank=True, verbose_name="Horarios de atención"),
        ),

        # 2. Medidas — rename largo → largo_aproximado
        migrations.RenameField(
            model_name="medidas",
            old_name="largo",
            new_name="largo_aproximado",
        ),

        # 3. Medidas — new extended fields
        migrations.AddField(
            model_name="medidas",
            name="bajo_busto",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name="Bajo busto"),
        ),
        migrations.AddField(
            model_name="medidas",
            name="largo_talle",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name="Largo talle"),
        ),
        migrations.AddField(
            model_name="medidas",
            name="hombro_pezon",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name="Hombro-pezón"),
        ),
        migrations.AddField(
            model_name="medidas",
            name="hombro_bajo_busto",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name="Hombro-bajo busto"),
        ),
        migrations.AddField(
            model_name="medidas",
            name="notas",
            field=models.TextField(blank=True),
        ),

        # 4. Novia — extended measurement fields
        migrations.AddField(
            model_name="novia",
            name="m_bajo_busto",
            field=models.CharField(blank=True, max_length=50, verbose_name="Bajo Busto"),
        ),
        migrations.AddField(
            model_name="novia",
            name="m_largo_talle",
            field=models.CharField(blank=True, max_length=50, verbose_name="Largo Talle"),
        ),
        migrations.AddField(
            model_name="novia",
            name="m_hombro_pezon",
            field=models.CharField(blank=True, max_length=50, verbose_name="Hombro-Pezón"),
        ),
        migrations.AddField(
            model_name="novia",
            name="m_hombro_bajo_busto",
            field=models.CharField(blank=True, max_length=50, verbose_name="Hombro-Bajo Busto"),
        ),

        # 5. Dama — extended measurement + date tracking fields
        migrations.AddField(
            model_name="dama",
            name="m_bajo_busto",
            field=models.CharField(blank=True, max_length=50, verbose_name="Bajo Busto"),
        ),
        migrations.AddField(
            model_name="dama",
            name="m_largo_talle",
            field=models.CharField(blank=True, max_length=50, verbose_name="Largo Talle"),
        ),
        migrations.AddField(
            model_name="dama",
            name="m_hombro_pezon",
            field=models.CharField(blank=True, max_length=50, verbose_name="Hombro-Pezón"),
        ),
        migrations.AddField(
            model_name="dama",
            name="m_hombro_bajo_busto",
            field=models.CharField(blank=True, max_length=50, verbose_name="Hombro-Bajo Busto"),
        ),
        migrations.AddField(
            model_name="dama",
            name="fecha_evento",
            field=models.DateField(blank=True, null=True, help_text="Fecha del evento de la dama"),
        ),
        migrations.AddField(
            model_name="dama",
            name="fecha_entrega",
            field=models.DateField(blank=True, null=True, help_text="Fecha de entrega del vestido"),
        ),
        migrations.AddField(
            model_name="dama",
            name="deadline_medidas",
            field=models.DateField(blank=True, null=True, help_text="Fecha límite para tomar medidas"),
        ),
        migrations.AddField(
            model_name="dama",
            name="medidas_tomadas",
            field=models.BooleanField(default=False, help_text="¿Ya se tomaron todas las medidas?"),
        ),

        # 6. Apartado — LLEGO_A_TIENDA estado + tracking fields
        migrations.AlterField(
            model_name="apartado",
            name="estado",
            field=models.CharField(
                choices=[
                    ("VIGENTE", "Vigente"),
                    ("VENCIDO", "Vencido"),
                    ("LLEGO_A_TIENDA", "Llegó a tienda"),
                    ("CANCELADO", "Cancelado"),
                    ("ENTREGADO", "Entregado"),
                ],
                default="VIGENTE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="apartado",
            name="llego_a_tienda_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="apartado",
            name="llego_a_tienda_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="apartados_llegaron",
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 7. Pedido — tracking fields
        migrations.AddField(
            model_name="pedido",
            name="llego_a_tienda_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pedido",
            name="llego_a_tienda_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pedidos_recibidos",
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 8. Ticket.tipo — add SERVICIO, ABONO
        migrations.AlterField(
            model_name="ticket",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("VENTA", "Venta"),
                    ("APARTADO", "Apartado"),
                    ("PEDIDO", "Pedido/Hechura"),
                    ("SERVICIO", "Servicio/Ajuste"),
                    ("ABONO", "Abono"),
                    ("AJUSTE", "Ajuste"),
                    ("DEVOLUCION", "Devolución"),
                ],
                default="VENTA",
                max_length=20,
            ),
        ),

        # 9. MovimientoCaja.tipo — add ABONO_SERVICIO
        migrations.AlterField(
            model_name="movimientocaja",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("VENTA", "Venta"),
                    ("ABONO_PEDIDO", "Abono de Pedido"),
                    ("ABONO_APARTADO", "Abono de Apartado"),
                    ("ABONO_SERVICIO", "Abono de Servicio"),
                    ("INGRESO", "Ingreso Extra"),
                    ("GASTO", "Gasto/Egreso"),
                    ("DEVOLUCION", "Devolución"),
                ],
                max_length=20,
            ),
        ),

        # 10. Servicio model
        migrations.CreateModel(
            name="Servicio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(
                    choices=[
                        ("AJUSTE", "Ajuste de vestido"),
                        ("COSTURA", "Costura / Arreglo"),
                        ("LAVADO", "Lavado"),
                        ("BORDADO", "Bordado"),
                        ("OTRO", "Otro servicio"),
                    ],
                    default="AJUSTE",
                    max_length=20,
                )),
                ("descripcion", models.TextField()),
                ("estado", models.CharField(
                    choices=[
                        ("RECIBIDO", "Recibido"),
                        ("EN_PROCESO", "En proceso"),
                        ("LISTO", "Listo para entrega"),
                        ("ENTREGADO", "Entregado"),
                        ("CANCELADO", "Cancelado"),
                    ],
                    db_index=True,
                    default="RECIBIDO",
                    max_length=20,
                )),
                ("costo", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("anticipo", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("fecha_prometida", models.DateField(blank=True, null=True)),
                ("notas", models.TextField(blank=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("cliente", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="servicios",
                    to="boutique.cliente",
                )),
                ("novia", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="servicios",
                    to="boutique.novia",
                )),
                ("creado_por", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-fecha_creacion"]},
        ),

        # 11. PagoServicio model
        migrations.CreateModel(
            name="PagoServicio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monto", models.DecimalField(decimal_places=2, max_digits=10)),
                ("metodo", models.CharField(
                    choices=[
                        ("EFECTIVO", "Efectivo"),
                        ("TARJETA", "Tarjeta"),
                        ("TRANSFERENCIA", "Transferencia"),
                    ],
                    default="EFECTIVO",
                    max_length=20,
                )),
                ("referencia", models.CharField(blank=True, max_length=100)),
                ("fecha", models.DateTimeField(auto_now_add=True)),
                ("notas", models.CharField(blank=True, max_length=200)),
                ("servicio", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="pagos_servicio",
                    to="boutique.servicio",
                )),
                ("registrado_por", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),

        # 12. Ticket.servicio FK
        migrations.AddField(
            model_name="ticket",
            name="servicio",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tickets",
                to="boutique.servicio",
            ),
        ),

        # 13. MovimientoCaja.servicio FK
        migrations.AddField(
            model_name="movimientocaja",
            name="servicio",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="boutique.servicio",
            ),
        ),
    ]
