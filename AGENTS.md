# Continuidad del POS de Adela

Leer `docs/VERSION_ESTABLE_2026-10-02.md`, `docs/COSTOS_GUIA_ADMIN.md` y `docs/COSTOS_NOTAS_TECNICAS.md` antes de tocar este proyecto.

- Producción y la referencia `stable/pos-2026-10-02` quedan congeladas en b50f9a7467026492b2a17655cc8401a135cc309f por instrucción de la usuaria.
- Costos se desarrolla exclusivamente en `feature/costos-inversion-2026-10-02`. No fusionar ni desplegar en el servicio actual sin una instrucción posterior.
- Conservar etiquetas/códigos físicos, conteo, modelos con fotos, variantes y movimientos. No recrear seriales ni resetear datos.
- Un costo desconocido es NULL, nunca cero. Una modificación de referencia afecta futuras entradas; cada venta guarda su costo histórico.
- Admin puede valorar; Vendedora no debe recibir costos en HTML ni API y no debe modificarlos enviando campos manualmente.
- Documentar alcance de pruebas y límites. No afirmar verificación visual, física o de IA real si solo se hicieron pruebas locales/mocks.
- El checkout local original puede estar desfasado del historial remoto; comparar con el SHA remoto y no publicar a ciegas todos los cambios locales.

## Simplificación UX posterior

La misma rama de desarrollo incorpora Entradas, Salidas, Buscar prendas y Etiquetas. Leer `docs/UX_ENTRADAS_SALIDAS.md`. Mantener esos nombres elegidos por la usuaria. No volver a usar «Preparar vestidos». La versión de Railway continúa congelada. No confundir borradores de sesión con órdenes de entrega compartidas o sincronizadas entre dispositivos.
