from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
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
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Asignar al grupo Vendedor por defecto
            vendedor_group = Group.objects.filter(name='Vendedor').first()
            if vendedor_group:
                user.groups.add(vendedor_group)
            login(request, user)
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'boutique/signup.html', {'form': form})
