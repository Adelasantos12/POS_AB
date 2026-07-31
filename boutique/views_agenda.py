"""
Vistas para Agenda, Novias y Catálogos
ByEasy POS - Adelé Boutique
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
import json
import calendar
from django.conf import settings

from .models import (
    Color, Tela, Novia, Dama, CitaAgenda,
    Producto, Modelo, registrar_auditoria, Pedido, PedidoItem, Apartado,
    MedidasDama, VestidoDama, MovimientoVestido, Cliente,
)
from .middleware import profile_permission_required
from .utils import safe_decimal
from .services.agenda_service import sync_delivery_with_agenda


# ============================================================
# CATÁLOGO DE COLORES Y TELAS
# ============================================================

@profile_permission_required('Inventario')
def catalogo_colores(request):
    """Vista del catálogo de colores con muestras visuales"""
    colores = Color.objects.filter(activo=True).order_by('familia', 'orden', 'nombre')
    familias = colores.values_list('familia', flat=True).distinct()
    
    # Agrupar por familia
    colores_por_familia = {}
    for familia in familias:
        colores_por_familia[familia] = colores.filter(familia=familia)
    
    return render(request, 'boutique/catalogo_colores.html', {
        'colores_por_familia': colores_por_familia,
        'total_colores': colores.count()
    })


@profile_permission_required('Inventario')
def catalogo_telas(request):
    """Vista del catálogo de telas"""
    telas = Tela.objects.filter(activa=True).order_by('nombre')
    
    return render(request, 'boutique/catalogo_telas.html', {
        'telas': telas,
        'total_telas': telas.count()
    })


@require_POST
@profile_permission_required(['Inventario', 'Vendedor'])
def api_color_editar(request, pk):
    """Edita un color"""
    color = get_object_or_404(Color, pk=pk)
    data = json.loads(request.body)
    try:
        color.nombre = data.get('nombre', color.nombre)
        color.codigo_hex = data.get('codigo_hex', color.codigo_hex)
        color.familia = data.get('familia', color.familia)
        color.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@profile_permission_required(['Inventario', 'Vendedor'])
def api_color_eliminar(request, pk):
    """Elimina un color"""
    color = get_object_or_404(Color, pk=pk)
    if color.es_predefinido:
        return JsonResponse({'status': 'error', 'message': 'No se pueden eliminar colores base'}, status=400)
    color.delete()
    return JsonResponse({'status': 'ok'})


@require_POST
@profile_permission_required(['Inventario', 'Vendedor'])
def api_crear_color(request):
    """Crear nuevo color con validación IA de similitud"""
    from .ai_utils import get_gemini_client
    from google.genai.errors import APIError

    data = json.loads(request.body)
    nombre = data.get('nombre', '').strip()
    codigo_hex = data.get('codigo_hex', '#CCCCCC')
    familia = data.get('familia', '')

    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)

    if Color.objects.filter(nombre__iexact=nombre).exists():
        return JsonResponse({'status': 'blocked', 'message': f'Ya existe un color llamado "{nombre}"'}, status=400)

    # Buscar colores similares para aviso IA (opcional — falla silenciosamente)
    colores_similares = Color.objects.filter(
        Q(nombre__icontains=nombre.split()[0]) | Q(familia__iexact=familia)
    ).values_list('nombre', flat=True)[:10]

    ai_warning = None
    if colores_similares:
        try:
            client = get_gemini_client()
            if client:
                from google.genai import types as _types
                prompt = f"""¿El color "{nombre}" es igual o muy similar a alguno de estos colores existentes?
Colores existentes: {', '.join(colores_similares)}

Responde SOLO con:
- "IGUAL: [nombre]" si es el mismo color con diferente escritura
- "SIMILAR: [nombre]" si es un tono muy parecido pero diferente
- "DIFERENTE" si es un color claramente distinto"""
                from django.conf import settings as _s
                from boutique.ai_utils import GEMINI_MODEL
                response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
                ai_response = response.text.strip()
                if 'IGUAL' in ai_response.upper():
                    return JsonResponse({'status': 'blocked', 'message': f'Este color parece ser igual a uno existente. {ai_response}'}, status=400)
                elif 'SIMILAR' in ai_response.upper():
                    ai_warning = ai_response
        except Exception:
            pass

    color = Color.objects.create(nombre=nombre, codigo_hex=codigo_hex, familia=familia, es_predefinido=False, activo=True)
    result = {'status': 'ok', 'id': color.id, 'nombre': color.nombre, 'message': f'Color "{nombre}" creado correctamente'}
    if ai_warning:
        result['warning'] = ai_warning
    return JsonResponse(result)


@require_POST
@profile_permission_required(['Inventario', 'Vendedor'])
def api_crear_tela(request):
    """Crear nueva tela con validación IA de similitud"""
    from .ai_utils import get_gemini_client, GEMINI_MODEL

    data = json.loads(request.body)
    nombre = data.get('nombre', '').strip()
    descripcion = data.get('descripcion', '')
    codigo_proveedor = data.get('codigo_proveedor', '')

    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)

    if Tela.objects.filter(nombre__iexact=nombre).exists():
        return JsonResponse({'status': 'blocked', 'message': f'Ya existe una tela llamada "{nombre}"'}, status=400)

    # Buscar telas similares para aviso IA (opcional — falla silenciosamente)
    telas_similares = Tela.objects.filter(
        Q(nombre__icontains=nombre.split()[0])
    ).values_list('nombre', flat=True)[:10]

    ai_warning = None
    if telas_similares:
        try:
            client = get_gemini_client()
            if client:
                prompt = f"""¿La tela "{nombre}" es igual o muy similar a alguna de estas telas existentes?
Telas existentes: {', '.join(telas_similares)}

Responde SOLO con:
- "IGUAL: [nombre]" si es la misma tela con diferente escritura
- "SIMILAR: [nombre]" si es muy parecida
- "DIFERENTE" si es claramente distinta"""
                response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
                ai_response = response.text.strip()
                if 'IGUAL' in ai_response.upper():
                    return JsonResponse({'status': 'blocked', 'message': f'Esta tela parece ser igual a una existente. {ai_response}'}, status=400)
                elif 'SIMILAR' in ai_response.upper():
                    ai_warning = ai_response
        except Exception:
            pass

    tela = Tela.objects.create(
        nombre=nombre,
        descripcion=descripcion,
        codigo_proveedor=codigo_proveedor or nombre[:3].upper(),
        proveedor=None,
        es_predefinida=False,
        activa=True
    )

    result = {'status': 'ok', 'id': tela.id, 'nombre': tela.nombre, 'message': f'Tela "{nombre}" creada correctamente'}
    if ai_warning:
        result['warning'] = ai_warning
    return JsonResponse(result)


@require_POST
@profile_permission_required(['Inventario', 'Vendedor'])
def api_tela_editar(request, pk):
    """Edita una tela"""
    tela = get_object_or_404(Tela, pk=pk)
    data = json.loads(request.body)
    try:
        tela.nombre = data.get('nombre', tela.nombre)
        tela.descripcion = data.get('descripcion', tela.descripcion)
        tela.codigo_proveedor = data.get('codigo_proveedor', tela.codigo_proveedor)
        tela.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@profile_permission_required(['Inventario', 'Vendedor'])
def api_tela_eliminar(request, pk):
    """Elimina una tela"""
    tela = get_object_or_404(Tela, pk=pk)
    if tela.es_predefinida:
        return JsonResponse({'status': 'error', 'message': 'No se pueden eliminar telas base'}, status=400)
    tela.delete()
    return JsonResponse({'status': 'ok'})


@login_required
def api_colores_list(request):
    """API que retorna lista de colores para selects"""
    colores = Color.objects.filter(activo=True).order_by('familia', 'orden')
    data = [{
        'id': c.id,
        'nombre': c.nombre,
        'hex': c.codigo_hex,
        'familia': c.familia
    } for c in colores]
    return JsonResponse({'colores': data})


@login_required
def api_telas_list(request):
    """API que retorna lista de telas para selects"""
    telas = Tela.objects.filter(activa=True).order_by('nombre')
    data = [{
        'id': t.id,
        'nombre': t.nombre,
        'descripcion': t.descripcion
    } for t in telas]
    return JsonResponse({'telas': data})


@login_required
def api_search_novias(request):
    """Busca novias por nombre o teléfono"""
    q = request.GET.get('q', '')
    if not q:
        return JsonResponse({'results': []})

    novias = Novia.objects.filter(
        Q(nombre__icontains=q) | Q(telefono__icontains=q)
    ).filter(activo=True)[:10]

    results = [{
        'id': n.id,
        'nombre': n.nombre,
        'telefono': n.telefono,
        'fecha_boda': n.fecha_boda.isoformat() if n.fecha_boda else None
    } for n in novias]

    return JsonResponse({'results': results})


@login_required
def api_get_damas_novia(request, novia_id):
    """Retorna las damas asociadas a una novia"""
    novia = get_object_or_404(Novia, pk=novia_id)
    damas = novia.damas.filter(activo=True).order_by('nombre')

    results = [{
        'id': d.id,
        'nombre': d.nombre,
        'talla': d.talla
    } for d in damas]

    return JsonResponse({'results': results})


# ============================================================
# AGENDA - CALENDARIO
# ============================================================

@profile_permission_required(['Agenda', 'Vendedor'])
def agenda_calendario(request):
    """Vista principal del calendario estilo iPhone"""
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    
    # Generar calendario del mes
    cal = calendar.Calendar(firstweekday=0)  # Lunes primero
    month_days = cal.monthdayscalendar(year, month)
    
    # Obtener citas del mes
    citas_mes = CitaAgenda.objects.filter(
        fecha__year=year,
        fecha__month=month
    ).select_related('novia')
    
    # Agrupar citas por día
    citas_por_dia = {}
    for cita in citas_mes:
        dia = cita.fecha.day
        if dia not in citas_por_dia:
            citas_por_dia[dia] = []
        citas_por_dia[dia].append(cita)
    
    # Nombres de meses en español
    meses = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    context = {
        'year': year,
        'month': month,
        'month_name': meses[month],
        'month_days': month_days,
        'citas_por_dia': citas_por_dia,
        'today': timezone.now().date(),
        'prev_month': month - 1 if month > 1 else 12,
        'prev_year': year if month > 1 else year - 1,
        'next_month': month + 1 if month < 12 else 1,
        'next_year': year if month < 12 else year + 1,
    }
    
    return render(request, 'boutique/agenda_calendario.html', context)


@profile_permission_required(['Agenda', 'Vendedor'])
def agenda_dia(request, year, month, day):
    """Vista de agenda por día - desglose por horas"""
    fecha = date(year, month, day)
    
    # Citas del día ordenadas por hora
    citas = CitaAgenda.objects.filter(fecha=fecha).order_by('hora_inicio').select_related('novia')
    
    # Generar slots de horas (9am - 8pm)
    horas = []
    for h in range(9, 21):
        hora_str = f"{h:02d}:00"
        citas_hora = [c for c in citas if c.hora_inicio.hour == h]
        horas.append({
            'hora': hora_str,
            'citas': citas_hora
        })
    
    # Nombres de días en español
    dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    meses = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
             'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    
    context = {
        'fecha': fecha,
        'dia_semana': dias_semana[fecha.weekday()],
        'mes_nombre': meses[month],
        'horas': horas,
        'citas': citas,
        'prev_day': fecha - timedelta(days=1),
        'next_day': fecha + timedelta(days=1),
    }
    
    return render(request, 'boutique/agenda_dia.html', context)


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_crear_cita(request):
    """Crear nueva cita en la agenda"""
    data = json.loads(request.body)
    
    titulo = data.get('titulo', '')
    tipo = data.get('tipo', 'CONSULTA')
    fecha_str = data.get('fecha')
    hora_inicio_str = data.get('hora_inicio')
    hora_fin_str = data.get('hora_fin')
    novia_id = data.get('novia_id')
    nombre_cliente = data.get('nombre_cliente', '')
    telefono_cliente = data.get('telefono_cliente', '')
    cantidad_damas = data.get('cantidad_damas', 0)
    notas = data.get('notas', '')
    
    if not titulo or not fecha_str or not hora_inicio_str:
        return JsonResponse({
            'status': 'error',
            'message': 'Título, fecha y hora son requeridos'
        }, status=400)
    
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
        hora_fin = datetime.strptime(hora_fin_str, '%H:%M').time() if hora_fin_str else None
    except ValueError as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Formato de fecha/hora inválido: {e}'
        }, status=400)
    
    novia = None
    if novia_id:
        try:
            novia = Novia.objects.get(pk=novia_id)
        except Novia.DoesNotExist:
            pass
    
    # Crear novia si se solicita
    if not novia and data.get('crear_novia') and nombre_cliente:
        fecha_boda_str = data.get('fecha_boda')
        if fecha_boda_str:
            try:
                fecha_boda = datetime.strptime(fecha_boda_str, '%Y-%m-%d').date()
                novia = Novia.objects.create(
                    nombre=nombre_cliente,
                    telefono=telefono_cliente,
                    fecha_boda=fecha_boda,
                    cantidad_damas=cantidad_damas,
                    creado_por=request.active_profile
                )
            except ValueError:
                pass

    cita = CitaAgenda.objects.create(
        titulo=titulo,
        tipo=tipo,
        fecha=fecha,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        novia=novia,
        nombre_cliente=nombre_cliente,
        telefono_cliente=telefono_cliente,
        cantidad_damas_esperadas=cantidad_damas,
        notas=notas,
        creado_por=request.active_profile
    )
    
    registrar_auditoria(
        usuario=request.active_profile,
        accion='CREACION_CITA',
        detalles=f'Cita creada: {titulo} - {fecha}',
        request=request
    )
    
    return JsonResponse({
        'status': 'ok',
        'id': cita.id,
        'message': f'Cita agendada para {fecha}'
    })


@login_required
def api_citas_rango(request):
    """API para obtener citas en un rango de fechas"""
    start = request.GET.get('start')
    end = request.GET.get('end')
    
    citas = CitaAgenda.objects.all()
    
    if start:
        citas = citas.filter(fecha__gte=start)
    if end:
        citas = citas.filter(fecha__lte=end)
    
    data = [{
        'id': c.id,
        'title': c.titulo,
        'start': f"{c.fecha}T{c.hora_inicio}",
        'end': f"{c.fecha}T{c.hora_fin}" if c.hora_fin else None,
        'tipo': c.tipo,
        'novia': c.novia.nombre if c.novia else None,
        'completada': c.completada
    } for c in citas.select_related('novia')]
    
    return JsonResponse({'citas': data})


# ============================================================
# NOVIAS Y PEDIDOS
# ============================================================

@profile_permission_required(['Agenda', 'Vendedor'])
def novias_list(request):
    """Lista de todas las novias activas con filtros y orden de urgencia"""
    q = request.GET.get('q', '')
    mes = request.GET.get('mes', '') # Formato YYYY-MM

    novias = Novia.objects.filter(activo=True)
    
    if q:
        novias = novias.filter(
            Q(nombre__icontains=q) | Q(telefono__icontains=q)
        )
    
    novias = novias.order_by('fecha_boda').prefetch_related(
        'pedidos', 'pedidos__pagos_pedido', 'damas'
    )
    
    return render(request, 'boutique/novias_list.html', {
        'novias': novias,
        'q': q
    })


@profile_permission_required(['Agenda', 'Vendedor'])
def novia_detalle(request, pk):
    """Detalle de una novia con su grupo y pedidos"""
    novia = get_object_or_404(Novia, pk=pk, activo=True)
    damas = novia.damas.filter(activo=True)
    pedidos = novia.pedidos.all().order_by('-fecha_creacion').select_related(
        'modelo', 'color', 'tela', 'cliente'
    ).prefetch_related('pagos_pedido')
    citas = novia.citas.all().order_by('fecha', 'hora_inicio')
    
    # Apartados vinculados
    from boutique.models import Apartado
    apartados_vinculados = Apartado.objects.filter(novia=novia).order_by('-fecha_creacion')

    # Resumen del grupo
    resumen = novia.resumen_grupo
    
    return render(request, 'boutique/novia_detalle.html', {
        'novia': novia,
        'damas': damas,
        'pedidos': pedidos,
        'citas': citas,
        'resumen': resumen,
        'apartados_vinculados': apartados_vinculados
    })


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_crear_novia(request):
    """Crear nueva novia"""
    data = json.loads(request.body)
    
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)
    
    fecha_boda_str = data.get('fecha_boda')
    if not fecha_boda_str:
        return JsonResponse({'status': 'error', 'message': 'La fecha de boda es requerida'}, status=400)
    
    try:
        fecha_boda = datetime.strptime(fecha_boda_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Formato de fecha inválido'}, status=400)
    
    novia = Novia.objects.create(
        nombre=nombre,
        telefono=data.get('telefono', ''),
        email=data.get('email', ''),
        fecha_boda=fecha_boda,
        fecha_prueba=datetime.strptime(data['fecha_prueba'], '%Y-%m-%d').date() if data.get('fecha_prueba') else None,
        fecha_entrega=datetime.strptime(data['fecha_entrega'], '%Y-%m-%d').date() if data.get('fecha_entrega') else None,
        fecha_limite=datetime.strptime(data['fecha_limite'], '%Y-%m-%d').date() if data.get('fecha_limite') else None,
        cantidad_damas=int(data.get('cantidad_damas', 0)),
        notas=data.get('notas', ''),
        modelo_especial=data.get('modelo_especial', ''),
        color_especial=data.get('color_especial', ''),
        tela_especial=data.get('tela_especial', ''),
        talla_especial=data.get('talla_especial', ''),
        creado_por=request.active_profile
    )
    
    # Sincronizar Agenda si tiene fecha de entrega
    if novia.fecha_entrega:
        sync_delivery_with_agenda(novia)
    
    return JsonResponse({
        'status': 'ok',
        'id': novia.id,
        'message': f'Novia "{nombre}" creada correctamente'
    })


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_agregar_dama(request, novia_id):
    """Agregar dama al grupo de la novia con auto-vinculación a Cliente"""
    from .models import Cliente
    novia = get_object_or_404(Novia, pk=novia_id)
    data = json.loads(request.body)
    
    nombre = data.get('nombre', '').strip()
    telefono = data.get('telefono', '').strip()
    email = data.get('email', '').strip()

    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)

    # 1. Gestionar Cliente
    cliente_obj = None
    if telefono:
        # Validar 10 dígitos (básico)
        digits = ''.join(filter(str.isdigit, telefono))
        if len(digits) != 10:
            return JsonResponse({'status': 'error', 'message': 'El teléfono debe tener 10 dígitos'}, status=400)

        cliente_obj, created = Cliente.objects.get_or_create(
            telefono=digits,
            defaults={'nombre': nombre, 'email': email}
        )
        if not created and not cliente_obj.email and email:
            cliente_obj.email = email
            cliente_obj.save(update_fields=['email'])

    # 2. Crear Dama
    dama = Dama.objects.create(
        novia=novia,
        cliente=cliente_obj,
        nombre=nombre,
        telefono=telefono,
        talla=data.get('talla', ''),
        modelo_especial=data.get('modelo_especial', ''),
        color_especial=data.get('color_especial', ''),
        tela_especial=data.get('tela_especial', ''),
        notas_ajustes=data.get('notas', '')
    )
    
    # Actualizar contador
    novia.cantidad_damas = novia.damas.filter(activo=True).count()
    novia.save(update_fields=['cantidad_damas'])
    
    return JsonResponse({
        'status': 'ok',
        'id': dama.id,
        'message': f'Dama "{dama.nombre}" agregada al grupo'
    })


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_editar_novia(request, pk):
    """Actualiza datos de una novia"""
    novia = get_object_or_404(Novia, pk=pk)
    data = json.loads(request.body)

    try:
        novia.nombre = data.get('nombre', novia.nombre)
        novia.telefono = data.get('telefono', novia.telefono)
        novia.email = data.get('email', novia.email)

        if data.get('fecha_boda'):
            novia.fecha_boda = datetime.strptime(data['fecha_boda'], '%Y-%m-%d').date()
        if data.get('fecha_prueba'):
            novia.fecha_prueba = datetime.strptime(data['fecha_prueba'], '%Y-%m-%d').date()
        if data.get('fecha_entrega'):
            novia.fecha_entrega = datetime.strptime(data['fecha_entrega'], '%Y-%m-%d').date()

        novia.modelo_especial = data.get('modelo_especial', novia.modelo_especial)
        novia.color_especial = data.get('color_especial', novia.color_especial)
        novia.tela_especial = data.get('tela_especial', novia.tela_especial)
        novia.talla_especial = data.get('talla_especial', novia.talla_especial)
        novia.notas = data.get('notas', novia.notas)

        novia.save()
        if novia.fecha_entrega:
            sync_delivery_with_agenda(novia)
        return JsonResponse({'status': 'ok', 'message': 'Novia actualizada'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_eliminar_novia(request, pk):
    """Soft delete de novia"""
    novia = get_object_or_404(Novia, pk=pk)
    novia.activo = False
    novia.save()
    return JsonResponse({'status': 'ok', 'message': 'Novia eliminada'})


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_editar_dama(request, pk):
    """Actualiza datos de una dama"""
    dama = get_object_or_404(Dama, pk=pk)
    data = json.loads(request.body)
    try:
        dama.nombre = data.get('nombre', dama.nombre)
        dama.telefono = data.get('telefono', dama.telefono)
        dama.talla = data.get('talla', dama.talla)
        dama.modelo_especial = data.get('modelo_especial', dama.modelo_especial)
        dama.color_especial = data.get('color_especial', dama.color_especial)
        dama.tela_especial = data.get('tela_especial', dama.tela_especial)
        dama.notas_ajustes = data.get('notas', dama.notas_ajustes)
        dama.save()
        return JsonResponse({'status': 'ok', 'message': 'Dama actualizada'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_eliminar_dama(request, pk):
    """Soft delete de dama"""
    dama = get_object_or_404(Dama, pk=pk)
    dama.activo = False
    dama.save()

    # Actualizar contador de la novia
    novia = dama.novia
    novia.cantidad_damas = novia.damas.filter(activo=True).count()
    novia.save(update_fields=['cantidad_damas'])

    return JsonResponse({'status': 'ok', 'message': 'Dama eliminada'})


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_crear_pedido(request):
    """Crea un pedido para novia o dama con ticket (Versión Simplificada)"""
    from .models import Pedido, Ticket
    from .services.cash_service import registrar_cobro, get_caja_activa
    data = json.loads(request.body)

    novia = get_object_or_404(Novia, pk=data.get('novia_id'))
    dama_id = data.get('dama_id')
    dama = get_object_or_404(Dama, pk=dama_id) if dama_id else None

    precio = safe_decimal(data.get('precio', 0))
    anticipo = safe_decimal(data.get('anticipo', 0))
    metodo = data.get('metodo', 'EFECTIVO')

    with transaction.atomic():
        pedido = Pedido.objects.create(
            novia=novia,
            dama=dama,
            es_vestido_novia=data.get('es_vestido_novia', False),
            precio=precio,
            anticipo=0, # Se registra vía registrar_cobro
            notas=data.get('notas', ''),
            fecha_entrega_estimada=data.get('fecha_entrega_estimada') or None,
            creado_por=request.active_profile
        )

        ticket = None
        if anticipo > 0:
            ticket = registrar_cobro(
                origen_tipo='pedido',
                origen_obj=pedido,
                monto=anticipo,
                metodo=metodo,
                usuario=request.active_profile,
                notas='Anticipo inicial'
            )
        else:
            caja = get_caja_activa()
            ticket = Ticket.objects.create(
                tipo='PEDIDO',
                novia=novia,
                cliente_nombre=dama.nombre if dama else novia.nombre,
                total=precio,
                total_pagado=0,
                cajero_nombre=request.active_profile.username,
                pedido=pedido,
                caja=caja
            )
            ticket.populate_from_obj(pedido)

        pedido.ticket = ticket
        pedido.save()

        if pedido.fecha_entrega_estimada:
            sync_delivery_with_agenda(pedido)

    return JsonResponse({
        'status': 'ok',
        'id': pedido.id,
        'ticket': ticket.folio,
        'message': f'Pedido generado con éxito. Ticket: {ticket.folio}'
    })


@require_POST
@profile_permission_required(['Agenda', 'Vendedor'])
def api_crear_pedido_completo(request):
    """Crea un pedido capturando todos los datos (modelo, color, talla, medidas, pago)"""
    from .models import Pedido, Ticket, Medidas, Modelo, Color, Cliente
    from .services.cash_service import registrar_cobro
    from .services.agenda_service import sync_delivery_with_agenda

    data = json.loads(request.body)
    novia = get_object_or_404(Novia, pk=data.get('novia_id'))
    dama_id = data.get('dama_id')
    dama = get_object_or_404(Dama, pk=dama_id) if dama_id else None

    precio = safe_decimal(data.get('precio', 0))
    anticipo = safe_decimal(data.get('anticipo', 0))
    metodo = data.get('metodo', 'EFECTIVO')
    tipo_ticket = 'PEDIDO' # Unificado para todos los pedidos de grupo

    with transaction.atomic():
        # 1. Resolver Cliente (Novia o Dama puede ser cliente)
        # Intentar vincular a un Cliente por teléfono si existe en Novia/Dama
        tel = dama.telefono if dama else novia.telefono
        nom = dama.nombre if dama else novia.nombre
        cliente_obj = None
        if tel:
            cliente_obj, _ = Cliente.objects.get_or_create(
                telefono=tel,
                defaults={'nombre': nom}
            )

        # 2. Resolver Modelo y Color si se proporcionaron nombres
        modelo_obj = None
        if data.get('modelo_nombre'):
            modelo_obj, _ = Modelo.objects.get_or_create(nombre=data['modelo_nombre'])

        color_obj = None
        if data.get('color_nombre'):
            color_obj, _ = Color.objects.get_or_create(nombre=data['color_nombre'])

        # 3. Crear Pedido
        pedido = Pedido.objects.create(
            novia=novia,
            dama=dama,
            cliente=cliente_obj,
            es_vestido_novia=data.get('es_vestido_novia', False),
            modelo=modelo_obj,
            color=color_obj,
            talla=data.get('talla', ''),
            precio=precio,
            anticipo=0, # Se actualizará vía PagoPedido
            notas=data.get('notas', ''),
            tipo_pedido='ESTANDAR_GRUPO', # Por defecto en flujo de grupo
            fecha_entrega_estimada=data.get('fecha_entrega_estimada') or None,
            creado_por=request.active_profile
        )

        # 4. Guardar Medidas (soportando ambos formatos de nombre: m_campo y campo)
        def _med(key, *aliases):
            for k in (key, *aliases):
                v = data.get(k)
                if v: return v
            return None

        m_busto             = _med('m_busto', 'busto')
        m_cintura           = _med('m_cintura', 'cintura')
        m_cadera            = _med('m_cadera', 'cadera')
        m_largo             = _med('m_largo', 'largo_aproximado', 'largo')
        m_bajo_busto        = _med('m_bajo_busto', 'bajo_busto')
        m_largo_talle       = _med('m_largo_talle', 'largo_talle')
        m_hombro_pezon      = _med('m_hombro_pezon', 'hombro_pezon')
        m_hombro_bajo_busto = _med('m_hombro_bajo_busto', 'hombro_bajo_busto')
        m_hombro            = _med('m_hombro', 'hombro')
        m_brazo             = _med('m_brazo', 'brazo')
        m_espalda           = _med('m_espalda', 'espalda')
        m_talle_del         = _med('m_talle_delantero', 'talle_delantero')
        m_talle_tras        = _med('m_talle_trasero', 'talle_trasero')
        m_altura_busto      = _med('m_altura_busto', 'altura_busto')
        m_sep_busto         = _med('m_separacion_busto', 'separacion_busto')
        m_notas             = _med('m_notas', 'notas_medidas', 'observaciones') or ''

        def _d(v):
            return safe_decimal(v, None) if v else None

        medidas = Medidas.objects.create(
            pedido=pedido,
            cliente=cliente_obj,
            cliente_nombre=nom,
            busto=_d(m_busto),
            cintura=_d(m_cintura),
            cadera=_d(m_cadera),
            largo_aproximado=_d(m_largo),
            bajo_busto=_d(m_bajo_busto),
            largo_talle=_d(m_largo_talle),
            hombro_pezon=_d(m_hombro_pezon),
            hombro_bajo_busto=_d(m_hombro_bajo_busto),
            hombro=_d(m_hombro),
            brazo=_d(m_brazo),
            espalda=_d(m_espalda),
            talle_delantero=_d(m_talle_del),
            talle_trasero=_d(m_talle_tras),
            altura_busto=_d(m_altura_busto),
            separacion_busto=_d(m_sep_busto),
            observaciones=m_notas
        )

        # 4.5 Crear VestidoDama si el pedido pertenece a una dama
        if dama:
            tipo_map = {
                'HECHURA': 'HECHURA', 'PEDIDO_EXTERNO': 'ESPECIAL',
                'ESTANDAR_GRUPO': 'CATALOGO', 'SOBRE_PEDIDO': 'ESPECIAL',
            }
            VestidoDama.objects.create(
                dama=dama,
                pedido=pedido,
                tipo=tipo_map.get(pedido.tipo_pedido, 'ESPECIAL'),
                modelo=modelo_obj,
                numero_modelo=data.get('numero_modelo', ''),
                descripcion_especial=data.get('descripcion_especial', ''),
                talla=data.get('talla', dama.talla or ''),
                color=color_obj,
                tela=pedido.tela,
                precio=precio,
                estado='PEDIDO',
                creado_por=request.active_profile,
            )

        # 5. Registrar Cobro (Genera Ticket y MovimientoCaja)
        ticket = None
        if anticipo > 0:
            try:
                ticket = registrar_cobro(
                    origen_tipo='pedido',
                    origen_obj=pedido,
                    monto=anticipo,
                    metodo=metodo,
                    usuario=request.active_profile,
                    notas='Anticipo inicial (Captura Completa)'
                )
            except ValueError as ve:
                # Si la caja está cerrada, lanzamos error para abortar transacción
                raise ve
        else:
            # Crear ticket sin pago si es necesario
            from .services.cash_service import get_caja_activa
            caja = get_caja_activa()
            ticket = Ticket.objects.create(
                tipo='PEDIDO',
                cliente_nombre=nom,
                total=precio,
                total_pagado=0,
                cajero_nombre=request.active_profile.username,
                pedido=pedido,
                novia=novia,
                caja=caja
            )
            ticket.populate_from_obj(pedido)

        pedido.ticket = ticket
        pedido.save()

        # Sincronizar Agenda
        if pedido.fecha_entrega_estimada:
            sync_delivery_with_agenda(pedido)

    return JsonResponse({
        'status': 'ok',
        'id': pedido.id,
        'ticket_folio': ticket.folio,
        'ticket_print_url': f"/api/tickets/{ticket.folio}/pdf/",
        'message': f'Pedido y ticket {ticket.folio} generados con éxito'
    })


# ============================================================
# PEDIDOS EN PUERTA - RESUMEN
# ============================================================

@profile_permission_required(['Agenda', 'Vendedor'])
def pedidos_en_puerta(request):
    """Tablero de taller/producción - Hechuras, Importaciones y Especiales"""
    from .models import Pedido
    from django.db.models import F

    q = request.GET.get('q', '')
    mes = request.GET.get('mes', '') # Formato YYYY-MM
    today = timezone.now().date()

    pedidos_qs = Pedido.objects.filter(
        ~Q(tipo_pedido='')  # todos los tipos
    ).exclude(
        estado__in=['ENTREGADO', 'CANCELADO']
    ).select_related(
        'novia', 'dama', 'color', 'tela', 'modelo', 'cliente'
    ).prefetch_related('pagos_pedido')

    if q:
        pedidos_qs = pedidos_qs.filter(
            Q(numero_ticket__icontains=q) |
            Q(novia__nombre__icontains=q) |
            Q(dama__nombre__icontains=q) |
            Q(cliente__nombre__icontains=q) |
            Q(cliente__telefono__icontains=q)
        )

    if mes:
        try:
            y, m = map(int, mes.split('-'))
            pedidos_qs = pedidos_qs.filter(fecha_entrega_estimada__year=y, fecha_entrega_estimada__month=m)
        except:
            pass

    # Orden por urgencia (próximas primero, nulas al final)
    pedidos_qs = pedidos_qs.order_by(F('fecha_entrega_estimada').asc(nulls_last=True))

    # Agrupar por tipo_pedido para el tablero
    pedidos_por_tipo = {}
    for t_code, t_label in Pedido.TIPOS_PEDIDO:
        pedidos_tipo = [p for p in pedidos_qs if p.tipo_pedido == t_code]
        if pedidos_tipo or not q:
            pedidos_por_tipo[t_code] = {
                'label': t_label,
                'pedidos': pedidos_tipo,
                'count': len(pedidos_tipo),
                'stats': {
                    'NUEVO': sum(1 for p in pedidos_tipo if p.estado == 'NUEVO'),
                    'EN_CONFECCION': sum(1 for p in pedidos_tipo if p.estado == 'EN_CONFECCION'),
                    'LISTO': sum(1 for p in pedidos_tipo if p.estado == 'LISTO'),
                    'SOLICITADO': sum(1 for p in pedidos_tipo if p.estado == 'SOLICITADO'),
                    'EN_PROCESO': sum(1 for p in pedidos_tipo if p.estado == 'EN_PROCESO'),
                    'POR_RECOGER': sum(1 for p in pedidos_tipo if p.estado == 'POR_RECOGER'),
                    'RECIBIDO': sum(1 for p in pedidos_tipo if p.estado == 'RECIBIDO'),
                }
            }
    
    return render(request, 'boutique/pedidos_en_puerta.html', {
        'pedidos_por_tipo': pedidos_por_tipo,
        'total_pedidos': pedidos_qs.count(),
        'q': q,
        'mes_actual': mes,
        'today': today
    })


# ============================================================
# RESUMEN NOCTURNO
# ============================================================

@profile_permission_required(['Agenda', 'Vendedor'])
def resumen_nocturno(request):
    """Resumen de citas para mañana y resto de la semana"""
    hoy = timezone.now().date()
    manana = hoy + timedelta(days=1)
    fin_semana = hoy + timedelta(days=7)
    
    citas_manana = CitaAgenda.objects.filter(
        fecha=manana
    ).order_by('hora_inicio').select_related('novia')
    
    citas_semana = CitaAgenda.objects.filter(
        fecha__gt=manana,
        fecha__lte=fin_semana
    ).order_by('fecha', 'hora_inicio').select_related('novia')
    
    # Agrupar citas de la semana por día
    citas_por_dia = {}
    for cita in citas_semana:
        if cita.fecha not in citas_por_dia:
            citas_por_dia[cita.fecha] = []
        citas_por_dia[cita.fecha].append(cita)
    
    return render(request, 'boutique/resumen_nocturno.html', {
        'manana': manana,
        'citas_manana': citas_manana,
        'citas_por_dia': citas_por_dia,
        'hoy': hoy
    })


# ============================================================
# EXPEDIENTE DE DAMA: DETALLE, MEDIDAS Y VESTIDO
# ============================================================

MEDIDAS_CAMPOS = [
    ('busto', 'Busto'), ('cintura', 'Cintura'), ('cadera', 'Cadera'),
    ('largo_aproximado', 'Largo aprox.'), ('hombro', 'Hombro'), ('brazo', 'Brazo'),
    ('espalda', 'Ancho espalda'), ('talle_delantero', 'Talle del.'), ('talle_trasero', 'Talle tras.'),
    ('bajo_busto', 'Bajo busto'), ('largo_talle', 'Largo talle'), ('hombro_pezon', 'Hombro-pezón'),
    ('hombro_bajo_busto', 'Hombro-bajo busto'), ('altura_busto', 'Altura busto'),
    ('separacion_busto', 'Separación busto'),
]


@login_required
@profile_permission_required(['Vendedor', 'Agenda', 'Admin', 'CEO'])
def dama_detalle(request, pk):
    """Ficha completa de una dama: medidas vigentes, vestido asignado, pagos, saldo."""
    import json as _json
    dama = get_object_or_404(Dama, pk=pk, activo=True)
    medidas_vigentes = dama.medidas_registradas.filter(vigente=True).first()
    vestido = dama.vestidos.first()  # None si no existe, evita EXISTS + SELECT doble
    pedidos = dama.pedidos.order_by('-fecha_creacion').select_related(
        'modelo', 'color', 'tela', 'cliente'
    ).prefetch_related('pagos_pedido')
    from django.db.models import Sum as _Sum
    agg = dama.pedidos.aggregate(
        total_precio=_Sum('precio'),
        total_pagado=_Sum('pagos_pedido__monto'),
    )
    total_precio = agg['total_precio'] or 0
    total_pagado = agg['total_pagado'] or 0
    saldo_total = total_precio - total_pagado

    medidas_vigentes_json = _json.dumps(medidas_vigentes.to_dict()) if medidas_vigentes else 'null'

    return render(request, 'boutique/dama_detalle.html', {
        'dama': dama,
        'novia': dama.novia,
        'medidas_vigentes': medidas_vigentes,
        'medidas_vigentes_json': medidas_vigentes_json,
        'medidas_campos': MEDIDAS_CAMPOS,
        'vestido': vestido,
        'pedidos': pedidos,
        'total_precio': total_precio,
        'total_pagado': total_pagado,
        'saldo_total': saldo_total,
    })


@login_required
def api_medidas_dama(request, pk):
    """GET: medidas vigentes. POST: crea versión (archiva la anterior)."""
    dama = get_object_or_404(Dama, pk=pk)

    if request.method == 'GET':
        m = dama.medidas_registradas.filter(vigente=True).first()
        return JsonResponse({'medidas': m.to_dict() if m else None})

    if request.method == 'POST':
        data = json.loads(request.body)
        campos = [
            'busto', 'cintura', 'cadera', 'largo_aproximado', 'hombro', 'brazo',
            'espalda', 'talle_delantero', 'talle_trasero', 'altura_busto',
            'separacion_busto', 'bajo_busto', 'largo_talle', 'hombro_pezon',
            'hombro_bajo_busto',
        ]
        with transaction.atomic():
            # Archivar versión anterior
            anterior = dama.medidas_registradas.filter(vigente=True).first()
            nueva_version = data.get('nueva_version', False)

            if anterior and not nueva_version:
                # Actualizar in-place la versión vigente
                for campo in campos:
                    if campo in data:
                        setattr(anterior, campo, safe_decimal(data[campo], None))
                anterior.notas = data.get('notas', anterior.notas)
                anterior.modificado_por = request.active_profile
                anterior.save()
                return JsonResponse({'status': 'ok', 'accion': 'actualizada', 'medidas': anterior.to_dict()})
            else:
                # Crear nueva versión; la anterior queda como histórica
                if anterior:
                    anterior.vigente = False
                    anterior.save(update_fields=['vigente'])
                kwargs = {
                    'dama': dama,
                    'vigente': True,
                    'notas': data.get('notas', ''),
                    'registrado_por': request.active_profile,
                    'modificado_por': request.active_profile,
                }
                for campo in campos:
                    if campo in data:
                        kwargs[campo] = safe_decimal(data[campo], None)
                nueva = MedidasDama.objects.create(**kwargs)
                return JsonResponse({'status': 'ok', 'accion': 'creada', 'medidas': nueva.to_dict()})

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


@login_required
def api_medidas_dama_historial(request, pk):
    """Devuelve todas las versiones de medidas de una dama, de más reciente a más antigua."""
    dama = get_object_or_404(Dama, pk=pk)
    historial = [m.to_dict() for m in dama.medidas_registradas.all()]
    return JsonResponse({'historial': historial, 'total': len(historial)})


@require_POST
@login_required
@profile_permission_required(['Vendedor', 'Agenda'])
def api_crear_vestido_dama(request, pk):
    """Crea un VestidoDama para la dama (normalmente llamado al crear el pedido)."""
    dama = get_object_or_404(Dama, pk=pk)
    data = json.loads(request.body)
    try:
        from .models import Modelo as ModeloObj, Color as ColorObj, Tela as TelaObj
        modelo_obj = None
        if data.get('modelo_id'):
            modelo_obj = ModeloObj.objects.filter(pk=data['modelo_id']).first()
        elif data.get('modelo_nombre'):
            modelo_obj, _ = ModeloObj.objects.get_or_create(nombre=data['modelo_nombre'])

        color_obj = None
        if data.get('color_id'):
            color_obj = ColorObj.objects.filter(pk=data['color_id']).first()
        elif data.get('color_nombre'):
            color_obj, _ = ColorObj.objects.get_or_create(nombre=data['color_nombre'])

        tela_obj = None
        if data.get('tela_id'):
            tela_obj = TelaObj.objects.filter(pk=data['tela_id']).first()
        elif data.get('tela_nombre'):
            tela_obj, _ = TelaObj.objects.get_or_create(nombre=data['tela_nombre'])

        pedido = None
        if data.get('pedido_id'):
            pedido = Pedido.objects.filter(pk=data['pedido_id']).first()

        tipo_map = {
            'HECHURA': 'HECHURA', 'PEDIDO_EXTERNO': 'ESPECIAL',
            'ESTANDAR_GRUPO': 'CATALOGO', 'SOBRE_PEDIDO': 'ESPECIAL',
        }
        tipo = tipo_map.get(pedido.tipo_pedido if pedido else '', data.get('tipo', 'ESPECIAL'))

        vestido = VestidoDama.objects.create(
            dama=dama,
            pedido=pedido,
            tipo=tipo,
            modelo=modelo_obj,
            numero_modelo=data.get('numero_modelo', ''),
            descripcion_especial=data.get('descripcion_especial', ''),
            talla=data.get('talla', dama.talla or ''),
            color=color_obj,
            tela=tela_obj,
            precio=safe_decimal(data.get('precio', 0)),
            costo=safe_decimal(data.get('costo', 0)),
            estado='HECHURA' if tipo == 'HECHURA' else 'PEDIDO',
            creado_por=request.active_profile,
        )
        return JsonResponse({'status': 'ok', 'vestido': vestido.to_dict()})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required(['Vendedor', 'Agenda', 'Admin'])
def api_vestido_llegada(request, pk):
    """Registra la llegada física del vestido a tienda (crea MovimientoVestido ENTRADA + RESERVA)."""
    vestido = get_object_or_404(VestidoDama, pk=pk)

    # Idempotencia: si ya llegó, no crear doble entrada
    if vestido.movimientos_vestido.filter(tipo='ENTRADA').exists():
        return JsonResponse({
            'status': 'error',
            'message': 'Ya existe una entrada registrada para este vestido. No se permite doble entrada.'
        }, status=400)

    data = json.loads(request.body) if request.body else {}
    notas = data.get('notas', '')

    with transaction.atomic():
        MovimientoVestido.objects.create(
            vestido=vestido,
            tipo='ENTRADA',
            cantidad=1,
            usuario=request.active_profile,
            notas=notas or 'Llegada a tienda',
        )
        MovimientoVestido.objects.create(
            vestido=vestido,
            tipo='RESERVA',
            cantidad=1,
            usuario=request.active_profile,
            notas=f'Reservado para {vestido.dama.nombre}',
        )
        vestido.estado = 'RESERVADO'
        vestido.llego_en = timezone.now()
        vestido.llego_por = request.active_profile
        vestido.save(update_fields=['estado', 'llego_en', 'llego_por'])

        # Si hay un pedido asociado, marcarlo como llegado a tienda
        if vestido.pedido:
            vestido.pedido.llego_a_tienda_en = timezone.now()
            vestido.pedido.llego_a_tienda_por = request.active_profile
            vestido.pedido.estado = 'POR_RECOGER'
            vestido.pedido.save(update_fields=['llego_a_tienda_en', 'llego_a_tienda_por', 'estado'])

    return JsonResponse({'status': 'ok', 'vestido': vestido.to_dict()})


@require_POST
@login_required
@profile_permission_required(['Vendedor', 'Caja'])
def api_vestido_entregar(request, pk):
    """Registra la entrega del vestido a la dama (MovimientoVestido SALIDA)."""
    vestido = get_object_or_404(VestidoDama, pk=pk)

    if vestido.estado == 'ENTREGADO':
        return JsonResponse({'status': 'error', 'message': 'El vestido ya fue entregado.'}, status=400)

    if not vestido.movimientos_vestido.filter(tipo='ENTRADA').exists():
        return JsonResponse({
            'status': 'error',
            'message': 'El vestido no ha llegado a tienda todavía. Registra la llegada primero.'
        }, status=400)

    if vestido.movimientos_vestido.filter(tipo='SALIDA').exists():
        return JsonResponse({'status': 'error', 'message': 'Ya existe una salida para este vestido.'}, status=400)

    data = json.loads(request.body) if request.body else {}

    with transaction.atomic():
        MovimientoVestido.objects.create(
            vestido=vestido,
            tipo='SALIDA',
            cantidad=1,
            usuario=request.active_profile,
            notas=data.get('notas', 'Entrega a dama'),
        )
        vestido.estado = 'ENTREGADO'
        vestido.entregado_en = timezone.now()
        vestido.entregado_por = request.active_profile
        vestido.save(update_fields=['estado', 'entregado_en', 'entregado_por'])

        if vestido.pedido:
            vestido.pedido.estado = 'ENTREGADO'
            vestido.pedido.fecha_entrega_real = timezone.now().date()
            vestido.pedido.save(update_fields=['estado', 'fecha_entrega_real'])

    return JsonResponse({'status': 'ok', 'vestido': vestido.to_dict()})


# ============================================================
# PEDIDOS — MÓDULO OPERATIVO COMPLETO
# ============================================================

@login_required
@profile_permission_required(['Agenda', 'Vendedor', 'Caja'])
def pedido_detalle(request, pk):
    """Vista operativa completa de un pedido."""
    pedido = get_object_or_404(
        Pedido.objects.select_related(
            'cliente', 'novia', 'dama', 'modelo', 'color', 'tela', 'creado_por'
        ).prefetch_related('items__modelo', 'items__color', 'items__tela', 'items__dama'),
        pk=pk,
    )
    pagos = pedido.pagos_pedido.order_by('fecha')
    total_pagado = sum(p.monto for p in pagos)
    saldo = pedido.precio - total_pagado
    today = timezone.now().date()

    # Medidas vigentes para la dama (si aplica)
    medidas_vigentes = None
    if pedido.dama:
        medidas_vigentes = pedido.dama.medidas_registradas.filter(vigente=True).first()

    colores = Color.objects.all().order_by('nombre')
    telas = Tela.objects.all().order_by('nombre')
    modelos = Modelo.objects.all().order_by('nombre')

    return render(request, 'boutique/pedido_detalle.html', {
        'pedido': pedido,
        'pagos': pagos,
        'total_pagado': total_pagado,
        'saldo': saldo,
        'today': today,
        'medidas_vigentes': medidas_vigentes,
        'colores': colores,
        'telas': telas,
        'modelos': modelos,
        'PEDIDO_ESTADOS': Pedido.ESTADOS,
        'ITEM_TIPOS': PedidoItem.TIPOS,
        'ITEM_ESTADOS': PedidoItem.ESTADOS,
    })


@login_required
@profile_permission_required(['Agenda', 'Vendedor', 'Caja'])
def pedido_nuevo(request):
    """Formulario unificado de creación de pedido."""
    cliente_id = request.GET.get('cliente_id')
    novia_id = request.GET.get('novia_id')
    dama_id = request.GET.get('dama_id')

    cliente = None
    novia = None
    dama = None

    if cliente_id:
        cliente = Cliente.objects.filter(pk=cliente_id).first()
    if novia_id:
        novia = Novia.objects.filter(pk=novia_id).first()
    if dama_id:
        dama = Dama.objects.select_related('novia').filter(pk=dama_id).first()
        if dama and not novia:
            novia = dama.novia

    colores = Color.objects.all().order_by('nombre')
    telas = Tela.objects.all().order_by('nombre')
    modelos = Modelo.objects.all().order_by('nombre')

    return render(request, 'boutique/pedido_nuevo.html', {
        'cliente': cliente,
        'novia': novia,
        'dama': dama,
        'colores': colores,
        'telas': telas,
        'modelos': modelos,
        'TIPOS_PEDIDO': Pedido.TIPOS_PEDIDO,
        'EVENTOS': Pedido.EVENTOS,
        'ITEM_TIPOS': PedidoItem.TIPOS,
    })


@require_POST
@login_required
@profile_permission_required(['Agenda', 'Vendedor', 'Caja'])
def api_pedido_nuevo(request):
    """Crea un Pedido completo con sus ítems desde el formulario unificado."""
    from .services import cash_service
    from .models import Ticket

    data = json.loads(request.body)

    # --- Cliente ---
    cliente_nombre = (data.get('cliente_nombre') or '').strip()
    cliente_telefono = (data.get('cliente_telefono') or '').strip()
    if not cliente_nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre del cliente es obligatorio.'}, status=400)

    cliente_obj = None
    if cliente_telefono:
        cliente_obj, _ = Cliente.objects.get_or_create(
            telefono=cliente_telefono,
            defaults={'nombre': cliente_nombre},
        )

    # --- Relaciones opcionales ---
    novia_obj = None
    dama_obj = None
    if data.get('novia_id'):
        novia_obj = Novia.objects.filter(pk=data['novia_id']).first()
    if data.get('dama_id'):
        dama_obj = Dama.objects.filter(pk=data['dama_id']).first()

    # --- Items ---
    items_data = data.get('items', [])
    if not items_data:
        return JsonResponse({'status': 'error', 'message': 'El pedido debe tener al menos un ítem.'}, status=400)

    precio_total = sum(
        float(it.get('precio', 0)) * int(it.get('cantidad', 1))
        for it in items_data
    )
    anticipo = float(data.get('anticipo', 0))

    with transaction.atomic():
        pedido = Pedido.objects.create(
            cliente=cliente_obj,
            novia=novia_obj,
            dama=dama_obj,
            tipo_pedido=data.get('tipo_pedido', 'SOBRE_PEDIDO'),
            evento=data.get('evento', ''),
            precio=precio_total,
            anticipo=anticipo,
            fecha_entrega_estimada=data.get('fecha_entrega_estimada') or None,
            fecha_evento=data.get('fecha_evento') or None,
            notas=data.get('notas', ''),
            creado_por=request.active_profile,
        )

        for it in items_data:
            item_dama = None
            if it.get('dama_id'):
                item_dama = Dama.objects.filter(pk=it['dama_id']).first()
            modelo_obj = None
            if it.get('modelo_id'):
                from .models import Modelo as _M
                modelo_obj = _M.objects.filter(pk=it['modelo_id']).first()
            color_obj = None
            if it.get('color_id'):
                color_obj = Color.objects.filter(pk=it['color_id']).first()
            tela_obj = None
            if it.get('tela_id'):
                tela_obj = Tela.objects.filter(pk=it['tela_id']).first()

            PedidoItem.objects.create(
                pedido=pedido,
                dama=item_dama or dama_obj,
                tipo=it.get('tipo', 'VESTIDO'),
                modelo=modelo_obj,
                numero_modelo=it.get('numero_modelo', ''),
                descripcion_especial=it.get('descripcion_especial', ''),
                talla=it.get('talla', ''),
                color=color_obj,
                tela=tela_obj,
                cantidad=int(it.get('cantidad', 1)),
                precio=float(it.get('precio', 0)),
                notas=it.get('notas', ''),
            )

        # Ticket inicial
        ticket = Ticket.objects.create(
            tipo='PEDIDO',
            cliente_nombre=cliente_nombre,
            cliente_telefono=cliente_telefono,
            total=precio_total,
            total_pagado=anticipo,
            cajero_nombre=request.active_profile.username,
            novia=novia_obj,
            pedido=pedido,
        )
        ticket.populate_from_obj(pedido)
        # populate_from_obj may clear cliente_nombre if Pedido has no such field — restore it
        if not ticket.cliente_nombre:
            ticket.cliente_nombre = cliente_nombre
            ticket.cliente_telefono = cliente_telefono
            _snap = ticket.snapshot_json or {}
            _snap['cliente'] = cliente_nombre
            _snap['cliente_telefono'] = cliente_telefono
            ticket.snapshot_json = _snap
            ticket.save(update_fields=['cliente_nombre', 'cliente_telefono', 'snapshot_json'])
        pedido.ticket = ticket
        pedido.save(update_fields=['ticket'])

        # Registrar anticipo si lo hay
        if anticipo > 0:
            metodo = data.get('metodo_pago', 'EFECTIVO')
            cash_service.registrar_cobro(
                origen_tipo='pedido',
                origen_obj=pedido,
                monto=anticipo,
                metodo=metodo,
                usuario=request.active_profile,
                notas='Anticipo inicial al crear pedido',
            )

    return JsonResponse({
        'status': 'ok',
        'pedido_id': pedido.pk,
        'folio': pedido.numero_ticket,
        'detalle_url': f'/pedidos/{pedido.pk}/',
    })


@require_POST
@login_required
@profile_permission_required(['Agenda', 'Vendedor'])
def api_pedido_editar(request, pk):
    """Edita campos del pedido (sin cambiar ítems)."""
    pedido = get_object_or_404(Pedido, pk=pk)
    try:
        data = json.loads(request.body)

        campos = ['evento', 'notas', 'notas_ajustes', 'notas_entrega', 'tipo_pedido']
        for c in campos:
            if c in data:
                setattr(pedido, c, data[c])

        if 'fecha_entrega_estimada' in data:
            pedido.fecha_entrega_estimada = data['fecha_entrega_estimada'] or None
        if 'fecha_evento' in data:
            pedido.fecha_evento = data['fecha_evento'] or None
        if 'precio' in data and data['precio'] not in ('', None):
            pedido.precio = safe_decimal(data['precio'])
        if 'estado' in data:
            pedido.estado = data['estado']

        pedido.save()
        return JsonResponse({'status': 'ok', 'precio': float(pedido.precio)})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON inválido'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required(['Agenda', 'Vendedor'])
def api_pedido_item_estado(request, pk):
    """Cambia el estado de un PedidoItem."""
    item = get_object_or_404(PedidoItem, pk=pk)
    data = json.loads(request.body)
    nuevo_estado = data.get('estado')
    if not nuevo_estado:
        return JsonResponse({'status': 'error', 'message': 'Estado requerido.'}, status=400)

    valid = [s[0] for s in PedidoItem.ESTADOS]
    if nuevo_estado not in valid:
        return JsonResponse({'status': 'error', 'message': 'Estado inválido.'}, status=400)

    with transaction.atomic():
        item.estado = nuevo_estado
        if nuevo_estado == 'LLEGO' and not item.llego_en:
            item.llego_en = timezone.now()
        if nuevo_estado == 'ENTREGADO' and not item.entregado_en:
            item.entregado_en = timezone.now()
        item.save()

    return JsonResponse({'status': 'ok', 'item': item.to_dict()})
