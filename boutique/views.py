from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def index(request):
    """
    Vista para la página de inicio principal.
    """
    # De momento, solo renderiza una plantilla estática de bienvenida.
    # En el futuro, aquí se podrá añadir lógica para mostrar
    # un dashboard, ventas recientes, etc.
    return render(request, 'boutique/index.html')
