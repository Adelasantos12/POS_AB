from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch
from django.contrib.auth.models import User
from functools import wraps
from django.core.exceptions import PermissionDenied

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
            active_profile_id = request.session.get('active_profile_id')
            if active_profile_id:
                try:
                    request.active_profile = User.objects.get(id=active_profile_id)
                except User.DoesNotExist:
                    if 'active_profile_id' in request.session:
                        del request.session['active_profile_id']
                    return redirect('seleccionar_perfil')
            else:
                if request.path not in exempt_paths and request.path != '/':
                    return redirect('seleccionar_perfil')

        return self.get_response(request)

def profile_permission_required(group_name):
    """
    Decorador para validar permisos contra el perfil activo en la sesión.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not hasattr(request, 'active_profile'):
                return redirect('seleccionar_perfil')

            # Superadmin o Admin tienen acceso total
            if (request.active_profile.is_superuser or
                request.active_profile.groups.filter(name__in=['Admin', 'Superadmin']).exists() or
                request.active_profile.groups.filter(name=group_name).exists()):
                return view_func(request, *args, **kwargs)

            raise PermissionDenied
        return _wrapped_view
    return decorator
