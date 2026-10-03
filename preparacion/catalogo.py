"""Explicit catalogue corrections; never regenerate SKU or change quantities."""
from django import forms
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, render, redirect
from boutique.models import Producto, Modelo, Categoria
from boutique.utils import normalizar_nombre
from .inversion import solo_admin


class CatalogoForm(forms.Form):
    nombre = forms.CharField(max_length=100, label='Nombre del modelo', widget=forms.TextInput(attrs={'placeholder':'1 hombro manga caída'}))
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.order_by('nombre'), label='Categoría (tipo de producto)')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


@solo_admin
def editar(request, producto_id):
    product = get_object_or_404(Producto.objects.select_related('modelo','categoria'), pk=producto_id)
    form = CatalogoForm(request.POST or None, initial={
        'nombre':product.modelo.nombre if product.modelo else product.rasgo1 or product.categoria.nombre,
        'categoria':product.categoria_id})
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                product = Producto.objects.select_for_update().get(pk=producto_id)
                name = normalizar_nombre(form.cleaned_data['nombre'])
                category = form.cleaned_data['categoria']
                if Modelo.objects.filter(nombre__iexact=name).exclude(pk=product.modelo_id).exists():
                    raise ValueError('Ya existe otro modelo con ese nombre. Usa un nombre distinto; esta acción no fusiona modelos.')
                if product.modelo_id:
                    model = Modelo.objects.select_for_update().get(pk=product.modelo_id)
                    model.nombre = name
                    model.categoria = category
                    model.save(update_fields=['nombre','categoria'])
                    Producto.objects.filter(modelo=model).update(categoria=category)
                else:
                    family = Producto.objects.filter(modelo__isnull=True,categoria_id=product.categoria_id,rasgo1=product.rasgo1) if product.rasgo1 else Producto.objects.filter(pk=product.pk)
                    # Preserve the existing family photo and original description.
                    model = Modelo.objects.create(nombre=name,categoria=category,
                        foto_principal=product.foto.name if product.foto else None,
                        descripcion=product.rasgo1,precio_sugerido=product.precio_venta,
                        costo_referencia=product.costo_referencia)
                    family.update(modelo=model,categoria=category)
            return redirect('inventario_view')
        except (ValueError, IntegrityError) as exc:
            form.add_error(None,str(exc))
    return render(request,'preparacion/editar_catalogo.html',{'form':form,'producto':product})
