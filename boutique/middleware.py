import uuid
import logging
from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib.auth.models import User
from django.core.cache import cache
from functools import wraps
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """Propaga un correlation ID por cada request para facilitar búsqueda en logs."""

    HEADER_IN = 'HTTP_X_REQUEST_ID'
    HEADER_OUT = 'X-Request-ID'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(self.HEADER_IN) or uuid.uuid4().hex[:12]
        request.request_id = request_id
        response = self.get_response(request)
        response[self.HEADER_OUT] = request_id
        return response


class ProfileMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Rutas que no requieren perfil activo
        try:
            exempt_paths = [
                reverse('login'),
                reverse('logout'),
                reverse('signup'),
                reverse('seleccionar_perfil'),
                reverse('autenticar_perfil'),
            ]
        except NoReverseMatch:
            exempt_paths = []

        # Permitir admin, estáticos y media siempre
        if request.path.startswith('/admin/') or request.path.startswith('/static/') or request.path.startswith('/media/'):
            return self.get_response(request)

        if request.user.is_authenticated:
            # Cache caja_activa for 30 s to avoid one extra query per request.
            caja_cache_key = 'caja_activa'
            request.caja_activa = cache.get(caja_cache_key)
            if request.caja_activa is None:
                from .models import CorteCaja
                request.caja_activa = CorteCaja.objects.filter(cerrado=False).first()
                cache.set(caja_cache_key, request.caja_activa, 30)

            active_profile_id = request.session.get('active_profile_id')
            if active_profile_id:
                try:
                    # prefetch_related('groups') avoids 2 extra queries in profile_permission_required
                    request.active_profile = User.objects.prefetch_related('groups').get(id=active_profile_id)
                except User.DoesNotExist:
                    if 'active_profile_id' in request.session:
                        del request.session['active_profile_id']
                    return redirect('seleccionar_perfil')
            else:
                if request.path not in exempt_paths and request.path != '/':
                    return redirect('seleccionar_perfil')

        return self.get_response(request)

def profile_permission_required(group_names):
    """
    Decorador para validar permisos contra el perfil activo en la sesión.
    Soporta un nombre de grupo (string) o una lista de nombres de grupo.
    """
    if isinstance(group_names, str):
        group_names = [group_names]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not hasattr(request, 'active_profile'):
                return redirect('seleccionar_perfil')

            # Superadmin, Admin, CEO o Supervisora tienen acceso total
            if (request.active_profile.is_superuser or
                request.active_profile.groups.filter(name__in=['Admin', 'Superadmin', 'CEO', 'Supervisora']).exists() or
                request.active_profile.groups.filter(name__in=group_names).exists()):
                return view_func(request, *args, **kwargs)

            raise PermissionDenied
        return _wrapped_view
    return decorator
