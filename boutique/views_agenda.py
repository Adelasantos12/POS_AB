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
    Producto, Modelo, registrar_auditoria
)
from .middleware import profile_permission_required


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
    from .ai_utils import get_gemini_model
    
    data = json.loads(request.body)
    nombre = data.get('nombre', '').strip()
    codigo_hex = data.get('codigo_hex', '#CCCCCC')
    familia = data.get('familia', '')
    
    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)
    
    # Verificar si ya existe exactamente
    if Color.objects.filter(nombre__iexact=nombre).exists():
        return JsonResponse({
            'status': 'blocked',
            'message': f'Ya existe un color llamado "{nombre}"'
        }, status=400)
    
    # Buscar colores similares para IA
    colores_similares = Color.objects.filter(
        Q(nombre__icontains=nombre.split()[0]) | Q(familia__iexact=familia)
    ).values_list('nombre', flat=True)[:10]
    
    ai_warning = None
    if colores_similares:
        model = get_gemini_model()
        if model:
            try:
                prompt = f"""¿El color "{nombre}" es igual o muy similar a alguno de estos colores existentes?
Colores existentes: {', '.join(colores_similares)}

Responde SOLO con:
- "IGUAL: [nombre]" si es el mismo color con diferente escritura
- "SIMILAR: [nombre]" si es un tono muy parecido pero diferente
- "DIFERENTE" si es un color claramente distinto"""

                response = model.generate_content(prompt)
                ai_response = response.text.strip()
                if 'IGUAL' in ai_response.upper():
                    return JsonResponse({
                        'status': 'blocked',
                        'message': f'Este color parece ser igual a uno existente. {ai_response}'
                    }, status=400)
                elif 'SIMILAR' in ai_response.upper():
                    ai_warning = ai_response
            except:
                pass
    
    # Crear el color
    color = Color.objects.create(
        nombre=nombre,
        codigo_hex=codigo_hex,
        familia=familia,
        es_predefinido=False,
        activo=True
    )
    
    response = {
        'status': 'ok',
        'id': color.id,
        'nombre': color.nombre,
        'message': f'Color "{nombre}" creado correctamente'
    }
    if ai_warning:
        response['warning'] = ai_warning
    
    return JsonResponse(response)


@require_POST
@profile_permission_required(['Inventario', 'Vendedor'])
def api_crear_tela(request):
    """Crear nueva tela con validación IA de similitud"""
    from .ai_utils import get_gemini_model
    
    data = json.loads(request.body)
    nombre = data.get('nombre', '').strip()
    descripcion = data.get('descripcion', '')
    codigo_proveedor = data.get('codigo_proveedor', '')
    
    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)
    
    # Verificar si ya existe
    if Tela.objects.filter(nombre__iexact=nombre).exists():
        return JsonResponse({
            'status': 'blocked',
            'message': f'Ya existe una tela llamada "{nombre}"'
        }, status=400)
    
    # Buscar telas similares
    telas_similares = Tela.objects.filter(
        Q(nombre__icontains=nombre.split()[0])
    ).values_list('nombre', flat=True)[:10]
    
    ai_warning = None
    if telas_similares:
        model = get_gemini_model()
        if model:
            try:
                prompt = f"""¿La tela "{nombre}" es igual o muy similar a alguna de estas telas existentes?
Telas existentes: {', '.join(telas_similares)}

Responde SOLO con:
- "IGUAL: [nombre]" si es la misma tela con diferente escritura
- "SIMILAR: [nombre]" si es muy parecida
- "DIFERENTE" si es claramente distinta"""

                response = model.generate_content(prompt)
                ai_response = response.text.strip()
                if 'IGUAL' in ai_response.upper():
                    return JsonResponse({
                        'status': 'blocked',
                        'message': f'Esta tela parece ser igual a una existente. {ai_response}'
                    }, status=400)
                elif 'SIMILAR' in ai_response.upper():
                    ai_warning = ai_response
            except:
                pass
    
    # Crear la tela
    from .models import Proveedor
    prov = Proveedor.objects.first()
    
    tela = Tela.objects.create(
        nombre=nombre,
        descripcion=descripcion,
        codigo_proveedor=codigo_proveedor or nombre[:3].upper(),
        proveedor=prov,
        es_predefinida=False,
        activa=True
    )
    
    response = {
        'status': 'ok',
        'id': tela.id,
        'nombre': tela.nombre,
        'message': f'Tela "{nombre}" creada correctamente'
    }
    if ai_warning:
        response['warning'] = ai_warning
    
    return JsonResponse(response)


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
    
    novias = novias.order_by('fecha_boda').prefetch_related('pedidos', 'damas')
    
    return render(request, 'boutique/novias_list.html', {
        'novias': novias,
        'q': q
    })


@profile_permission_required(['Agenda', 'Vendedor'])
def novia_detalle(request, pk):
    """Detalle de una novia con su grupo y pedidos"""
    novia = get_object_or_404(Novia, pk=pk, activo=True)
    damas = novia.damas.filter(activo=True)
    pedidos = novia.pedidos.all().order_by('-fecha_creacion')
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
    
    # Crear cita de entrega automática si hay fecha
    if novia.fecha_entrega:
        CitaAgenda.objects.create(
            titulo=f"Entrega - {novia.nombre}",
            tipo='ENTREGA',
            fecha=novia.fecha_entrega,
            hora_inicio=datetime.strptime('11:00', '%H:%M').time(),
            novia=novia,
            creado_por=request.active_profile
        )
    
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

    precio = Decimal(str(data.get('precio', 0)))
    anticipo = Decimal(str(data.get('anticipo', 0)))
    metodo = data.get('metodo', 'EFECTIVO')

    with transaction.atomic():
        pedido = Pedido.objects.create(
            novia=novia,
            dama=dama,
            es_vestido_novia=data.get('es_vestido_novia', False),
            precio=precio,
            anticipo=0, # Se registra vía registrar_cobro
            notas=data.get('notas', ''),
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

    data = json.loads(request.body)
    novia = get_object_or_404(Novia, pk=data.get('novia_id'))
    dama_id = data.get('dama_id')
    dama = get_object_or_404(Dama, pk=dama_id) if dama_id else None

    precio = Decimal(str(data.get('precio', 0)))
    anticipo = Decimal(str(data.get('anticipo', 0)))
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
            creado_por=request.active_profile
        )

        # 4. Guardar Medidas (soportando ambos formatos de nombre)
        m_busto = data.get('m_busto') or data.get('busto')
        m_cintura = data.get('m_cintura') or data.get('cintura')
        m_cadera = data.get('m_cadera') or data.get('cadera')
        m_largo = data.get('m_largo') or data.get('largo')
        m_notas = data.get('m_notas') or data.get('notas_medidas', '')

        medidas = Medidas.objects.create(
            pedido=pedido,
            cliente=cliente_obj,
            cliente_nombre=nom,
            busto=Decimal(str(m_busto)) if m_busto else None,
            cintura=Decimal(str(m_cintura)) if m_cintura else None,
            cadera=Decimal(str(m_cadera)) if m_cadera else None,
            largo=Decimal(str(m_largo)) if m_largo else None,
            observaciones=m_notas
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

    # Tipos que requieren seguimiento externo (según ajuste de alcance)
    tipos_seguimiento = ['HECHURA', 'PEDIDO_EXTERNO']

    pedidos_qs = Pedido.objects.filter(
        tipo_pedido__in=tipos_seguimiento
    ).exclude(
        estado__in=['ENTREGADO', 'CANCELADO']
    ).select_related('novia', 'dama', 'color', 'tela', 'modelo', 'cliente')

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
        if t_code in tipos_seguimiento:
            pedidos_tipo = [p for p in pedidos_qs if p.tipo_pedido == t_code]
            if pedidos_tipo or not q: # Mostrar siempre si no hay búsqueda
                pedidos_por_tipo[t_code] = {
                    'label': t_label,
                    'pedidos': pedidos_tipo,
                    'count': len(pedidos_tipo),
                    # Contadores por estado específicos para este tipo
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
