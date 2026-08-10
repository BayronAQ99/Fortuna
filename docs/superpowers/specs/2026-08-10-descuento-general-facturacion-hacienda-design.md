# Descuento general en facturación — compatibilidad con Hacienda y limpieza de botones de Preventas

- **Fecha:** 2026-08-10
- **Estado:** Aprobado (diseño)
- **Alcance:** Corregir el wizard existente `distribuidora.factura.descuento.wizard` (módulo `distribuidora_ventas`) para que el descuento general sea compatible con el envío de facturas a Hacienda (`l10n_cr_fe_crlibre`), y quitar del formulario de Orden de venta los botones de `sale_loyalty` que no se van a usar.

---

## 1. Contexto

El 2026-07-20 se implementó `distribuidora.factura.descuento.wizard`: un botón "Descuento general" en la factura de cliente que aplica un % de descuento creando una línea nueva con un producto genérico "Descuento" (reutilizando `company.sale_discount_product_id`, el mismo mecanismo que usa el asistente nativo de Preventas `sale.order.discount`, modo "Global Discount"). Ese trabajo está mergeado en `19.0` pero el módulo no estaba instalado en la base `Fortuna`.

Al retomar esta funcionalidad se detectó un conflicto con `l10n_cr_fe_crlibre` (la integración de facturación electrónica con Hacienda), confirmado que es la misma empresa/flujo:

- `_l10n_cr_fe_build_detalles()` (`addons/l10n_cr_fe_crlibre/models/account_move.py`) exige que **todo** `account.move.line` de tipo `product` tenga un producto con código CABYS asignado, o lanza `UserError` al intentar enviar la factura a Hacienda. El producto "Descuento" que crea el wizard no tiene CABYS — cualquier factura con este tipo de descuento fallaría al enviarse.
- Conceptualmente, el esquema v4.4 de Hacienda no modela el descuento como una línea de producto aparte: cada línea de detalle (`LineaDetalle`) tiene su propio campo `MontoDescuento`. Una "línea de descuento" separada no tiene equivalente natural en ese esquema.
- Aparte, se descubrió que `_l10n_cr_fe_build_detalles()` **ya ignoraba** el campo nativo `discount` de `account.move.line` incluso antes de este cambio — es un hueco preexistente que afecta a cualquier factura donde alguien haya usado manualmente la columna "Desc.%" (ya visible/usable en facturas hoy).

Por separado, al investigar el botón "Descuento" de Preventas se confirmó que es una función nativa del módulo `sale` (wizard `sale.order.discount`, visible con el grupo `sale.group_discount_per_so_line`, ya activo) — **no depende de `sale_loyalty`**. Los botones "Código de cupón" y "Recompensa" sí son exclusivos de `sale_loyalty`, instalado por error en esta sesión y sin ningún caso de uso real todavía.

## 2. Objetivo y definición de "hecho"

1. En Orden de venta, solo debe verse el botón "Descuento" — sin "Código de cupón" ni "Recompensa".
2. En una factura de cliente en borrador, el botón "Descuento general" debe aplicar el % escribiendo el campo `discount` de cada línea de producto existente (sin crear líneas nuevas ni productos sin CABYS).
3. El XML que genera `l10n_cr_fe_crlibre` para una factura con líneas descontadas debe traer `MontoDescuento` correcto por línea, con `montoTotal - montoDescuento = subTotal` reconciliado.

**Éxito =** con una factura de prueba de 2-3 líneas con IVA, aplicar 10% de descuento general dejar cada línea con `discount == 10.0`, el total baja el 10% correspondiente, y el XML generado para Hacienda trae `MontoDescuento` por línea sin necesitar ningún producto adicional ni romper por falta de CABYS.

## 3. Diseño

### 3.1 Preventas — quitar botones de `sale_loyalty`

Desinstalar el módulo `sale_loyalty` de la base `Fortuna` (acción de configuración, no cambio de código — no hay ningún dato de este módulo en uso todavía). El botón "Descuento" permanece porque pertenece a `sale`.

### 3.2 Reescribir `distribuidora.factura.descuento.wizard`

`addons/distribuidora_ventas/wizards/factura_descuento_wizard.py`:

- Se mantiene el campo `porcentaje` (Float, 0-100) y sus validaciones (`_check_porcentaje`) sin cambios.
- `action_aplicar()` cambia de "crear línea de descuento nueva" a **escribir `discount` en cada línea de producto existente**:
  ```python
  def action_aplicar(self):
      self.ensure_one()
      product_lines = self.move_id.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
      product_lines.write({'discount': self.porcentaje})
  ```
- Se elimina `_get_discount_product()` — ya no se necesita ningún producto de descuento ni dependencia de `company.sale_discount_product_id`.
- El botón, la acción, la vista del wizard y el permiso (`ir.model.access.csv`) no cambian — solo cambia qué hace `action_aplicar`.

### 3.3 Tests de `distribuidora_ventas` a actualizar

`tests/test_factura_descuento_wizard.py`:
- `test_applies_percentage_discount_with_correct_taxes` cambia su aserción: en vez de buscar una línea con `product_id == company.sale_discount_product_id`, verifica que cada línea de producto original tiene `discount == 10.0` y que `amount_untaxed` bajó a 1800.0.
- `test_rejects_percentage_over_100` y `test_rejects_zero_percentage` no cambian (validan el wizard antes de aplicar).

`tests/test_factura_descuento_wizard_view.py` no necesita cambios — sigue verificando que el botón existe y apunta a la acción correcta, y que la columna `discount` es visible por defecto.

### 3.4 Fix en `l10n_cr_fe_crlibre` — `MontoDescuento` por línea

`addons/l10n_cr_fe_crlibre/models/account_move.py`, método `_l10n_cr_fe_build_detalles()`:

- Cuando `line.discount` es distinto de cero, calcular el monto de descuento en colones: `monto_descuento = (line.price_unit * line.quantity) - line.price_subtotal` (equivalente a aplicar el % sobre el bruto de la línea, coherente con cómo Odoo ya calcula `price_subtotal`).
- Agregar al diccionario `detalle` la clave de descuento correspondiente solo cuando `monto_descuento > 0`, sin romper la estructura para líneas sin descuento.
- `montoTotal` sigue siendo el bruto (`price_unit * quantity`); con el descuento presente, `montoTotal - montoDescuento == subTotal` queda reconciliado, que es lo que hoy falla silenciosamente.

**Punto abierto, no resuelto en este spec:** revisé `docs/superpowers/plans/notes/api-samples.md` (la única documentación de la API de CRLibre que existe en el repo) y **no menciona ningún campo de descuento** — la lista de claves requeridas/conocidas para `gen_xml_fe` (`codigoCABYS`, `subTotal`, `impuestoAsumidoEmisorFabrica`, `impuestoNeto`, `cantidad`, `unidadMedida`, `detalle`, `precioUnitario`, `montoTotal`, `montoTotalLinea`, `impuesto[]`) no incluye nada de descuento. No hay forma de confirmar el nombre exacto del campo (`montoDescuento` es una suposición razonable por el esquema oficial de Hacienda v4.4, pero CRLibre podría envolverlo distinto) sin probarlo contra la API real — mismo método que ya se usó en el plan de nota de débito y en el spec original de este mismo descuento ("prototipado en vivo contra una factura real", no solo leído del código).

El plan de implementación debe incluir un paso explícito de prototipado contra el sandbox de CRLibre (`crlibre-app`/`crlibre-mariadb`, ya corriendo en Docker) antes de escribir el fix definitivo, para confirmar el nombre del campo y si Hacienda espera algo adicional (p. ej. naturaleza del descuento). Si el prototipado no es posible en el tiempo disponible, este punto queda como un TODO explícito y documentado en el código (no una suposición silenciosa) — mejor no enviar el campo que enviarlo con un nombre incorrecto sin detectarlo.

Se necesita un test unitario nuevo en `addons/l10n_cr_fe_crlibre/tests/` (archivo a determinar en el plan de implementación) que arme una factura con una línea con `discount=10`, llame `_l10n_cr_fe_build_detalles()` y verifique que el monto de descuento, `montoTotal` y `subTotal` reconcilian.

## 4. Fuera de alcance

- Modo "monto fijo" o "descuento como línea nueva" del wizard de factura — se reemplaza por completo por el modo "por línea", no coexisten.
- Cambios en Preventas (`sale.order`) más allá de desinstalar `sale_loyalty` — el botón/wizard nativo `sale.order.discount` sigue igual.
- Descuento en facturas de proveedor — sigue limitado a `out_invoice`/`out_refund`, sin cambios ahí.
- Reinstalar o construir de nuevo un mecanismo de "línea de descuento como producto" — el hallazgo de este spec es que ese patrón no es compatible con el modelo de Hacienda para este negocio.

## 5. Estrategia de pruebas

- Suite de `distribuidora_ventas` completa (tests existentes actualizados + los que ya pasaban) en verde.
- Test nuevo en `l10n_cr_fe_crlibre` para `MontoDescuento` en `_l10n_cr_fe_build_detalles()`.
- Suite completa de `l10n_cr_fe_crlibre` (la que ya está en 208 tests / 168 post-tests) sigue en verde tras el cambio.
- Verificación manual: instalar `distribuidora_ventas` en `Fortuna`, crear factura de cliente en borrador con 2-3 líneas, aplicar 10% de descuento general, confirmar el total y (si es posible sin enviar de verdad a Hacienda) inspeccionar el XML/diccionario de detalle generado.
- Confirmar en el navegador que Preventas solo muestra el botón "Descuento" tras desinstalar `sale_loyalty`.
