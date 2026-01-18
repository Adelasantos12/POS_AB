from django.shortcuts import render, redirect
from .forms import CustomUserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import Group

def index(request):
    """
    Vista para la página de inicio principal.
    """
    # De momento, solo renderiza una plantilla estática de bienvenida.
    # En el futuro, aquí se podrá añadir lógica para mostrar
    # un dashboard, ventas recientes, etc.
    return render(request, 'boutique/index.html')

def signup(request):
    """
    Vista para el registro de nuevos usuarios.
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Asignar al grupo Vendedor por defecto
            # Usamos get_or_create para evitar el error 500 si el grupo no existe aún
            vendedor_group, _ = Group.objects.get_or_create(name='Vendedor')
            user.groups.add(vendedor_group)
            login(request, user)
            return redirect('index')
    else:
        form = CustomUserCreationForm()
    return render(request, 'boutique/signup.html', {'form': form})
