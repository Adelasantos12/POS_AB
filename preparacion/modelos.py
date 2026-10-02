"""Model creation before variants, using the existing model/photo fields."""
from django import forms
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from boutique.middleware import profile_permission_required
from boutique.models import Modelo, Categoria
from boutique.utils import normalizar_nombre


class ModeloForm(forms.ModelForm):
    class Meta:
        model = Modelo
        fields = ['foto_principal', 'nombre', 'categoria', 'combinacion_telas', 'descripcion', 'referencia', 'notas_confeccion']
        labels = {'foto_principal': 'Foto del modelo', 'nombre': 'Nombre del modelo',
                  'categoria': 'Categoría', 'combinacion_telas': 'Tela o combinación de telas',
                  'descripcion': 'Características', 'referencia': 'Referencia (opcional)',
                  'notas_confeccion': 'Notas de confección (opcional)'}
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3}),
                   'combinacion_telas': forms.TextInput(),
                   'notas_confeccion': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].required = True
        self.fields['categoria'].queryset = Categoria.objects.order_by('nombre')
        for name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-select' if name == 'categoria' else 'form-control'
        self.fields['foto_principal'].widget.attrs['accept'] = 'image/*'

    def clean_nombre(self):
        nombre = normalizar_nombre(self.cleaned_data['nombre'])
        if Modelo.objects.filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError('Este modelo ya existe. Agrega sus variantes desde Inventario o continúa con él abajo.')
        return nombre


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def agregar_modelo(request):
    form = ModeloForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                modelo = form.save()
            return redirect(f'{reverse("preparacion:inicio")}?modelo={modelo.pk}#nuevo')
        except IntegrityError:
            form.add_error('nombre', 'Ese modelo ya existe. Continúa con el modelo guardado.')
    return render(request, 'preparacion/agregar_modelo.html', {
        'form': form, 'pendientes': Modelo.objects.filter(producto__isnull=True).order_by('nombre')
    })


class GrupoModelos(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        if not self.forms:
            raise forms.ValidationError('Selecciona al menos una foto.')
        nombres = [f.cleaned_data['nombre'].casefold() for f in self.forms]
        if len(nombres) != len(set(nombres)):
            raise forms.ValidationError('Hay nombres repetidos en el grupo. Cada ficha debe corresponder a un modelo diferente.')
        for form in self.forms:
            if not form.cleaned_data.get('foto_principal'):
                raise forms.ValidationError('Cada modelo del grupo necesita su foto. Vuelve a elegir las fotos si hubo errores.')


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def agregar_modelos_bloque(request):
    Factory = forms.formset_factory(ModeloForm, formset=GrupoModelos, extra=0,
        min_num=0, max_num=20, validate_max=True, absolute_max=20)
    grupo = Factory(request.POST or None, request.FILES or None, prefix='modelos')
    guardados = []
    error = None
    if request.method == 'POST' and grupo.is_valid():
        try:
            with transaction.atomic():
                for form in grupo:
                    guardados.append(form.save())
            # Render the saved models directly: refresh redirects to the safe GET list.
            return redirect(reverse('preparacion:agregar_modelos_bloque') + '?guardados=' + ','.join(str(m.pk) for m in guardados))
        except IntegrityError:
            error = 'Un nombre ya existe. No se guardó ningún modelo. Revisa los nombres y vuelve a elegir las fotos.'
    ids = [int(i) for i in request.GET.get('guardados', '').split(',') if i.isdigit()][:20]
    return render(request, 'preparacion/modelos_bloque.html', {'grupo': grupo,
        'guardados': Modelo.objects.filter(pk__in=ids).order_by('pk'), 'error': error})
