# Descuento general en facturación — compatibilidad con Hacienda — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el botón "Descuento general" en la factura de cliente aplique el % escribiendo el campo nativo `discount` de cada línea (sin crear una línea/producto sin CABYS), que el XML que se envía a Hacienda refleje ese descuento por línea, y que en Preventas solo quede visible el botón "Descuento" nativo (sin "Código de cupón"/"Recompensa" de `sale_loyalty`).

**Architecture:** Se reescribe `distribuidora.factura.descuento.wizard` (ya existente en `addons/distribuidora_ventas/`) para que `action_aplicar()` escriba `discount` en cada `account.move.line` de tipo `'product'`, eliminando el mecanismo de línea-de-producto-descuento. Se corrige `_l10n_cr_fe_build_detalles()` en `addons/l10n_cr_fe_crlibre/models/account_move.py` para incluir el descuento por línea en el payload que se envía a la API de CRLibre — el nombre exacto de ese campo se confirma primero contra el sandbox local de CRLibre (contenedor `crlibre-app`, ya corriendo, `gen_xml_fe` no envía nada a Hacienda real). Por último se desinstala `sale_loyalty` de la base `Fortuna` (acción de configuración, sin código).

**Tech Stack:** Odoo 19 (Python 3.10-3.14) corriendo en Docker (`fortuna-odoo-1` / `fortuna-db-1`, base `Fortuna`), `odoo.tests.common.TransactionCase`, `unittest.mock` donde aplique.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-10-descuento-general-facturacion-hacienda-design.md`.
- Imports ordenados: future → stdlib → third-party → odoo → odoo.addons (lo aplica `ruff`).
- Tests con `@tagged('post_install', '-at_install')`, `TransactionCase`, igual que el resto de `distribuidora_ventas` y `l10n_cr_fe_crlibre`.
- No se toca `sale.order`/Preventas más allá de desinstalar `sale_loyalty` — el wizard nativo `sale.order.discount` sigue igual (spec §3.1, §4).
- Solo modo "por línea" en el wizard de factura — se elimina por completo el mecanismo de línea-de-producto-descuento, no coexisten ambos (spec §3.2, §4).
- Solo facturas de cliente (`out_invoice`/`out_refund`) — sin cambios en facturas de proveedor (spec §4, ya así en el código existente).
- **Comandos de esta sesión, verificados y en uso:**
  - Correr tests de un módulo: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /<modulo>:<Clase> --stop-after-init --http-port=8169 -u <modulo>` (el puerto 8069 ya está ocupado por el proceso principal, por eso `--http-port=8169` en corridas de test).
  - Actualizar módulo sin tests: mismo comando sin `--test-enable --test-tags`.
  - Después de cualquier `-u <modulo>` en una ejecución aparte, correr `docker restart fortuna-odoo-1` para que el proceso que sirve `localhost:8069` recargue el registro — si no, el navegador tira errores de campo "undefined" sobre campos/vistas nuevas.
  - Instalar/desinstalar un módulo: mismo patrón con `-i <modulo>` (instalar). Para desinstalar no hay flag de línea de comandos directo — se hace escribiendo el estado en el modelo `ir.module.module` vía `odoo shell` (ver Task 1).
  - `docker exec -i fortuna-odoo-1 odoo shell -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --http-port=8169 --no-http` acepta un script Python por stdin (con `-i` en `docker exec`, no en `odoo shell`) para ejecutar código puntual contra el ORM sin abrir una sesión interactiva.

---

### Task 1: Desinstalar `sale_loyalty` de la base `Fortuna`

**Files:** ninguno (acción de configuración vía `odoo shell`, sin cambios de código).

**Interfaces:** ninguna — tarea independiente del resto del plan.

- [ ] **Step 1: Desinstalar el módulo vía `odoo shell`**

Run (nota: `-i` es una bandera de `docker exec` para pipear stdin, no de `odoo shell`):

```bash
MSYS_NO_PATHCONV=1 docker exec -i fortuna-odoo-1 odoo shell -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --http-port=8169 --no-http <<'EOF'
module = env['ir.module.module'].search([('name', '=', 'sale_loyalty')])
module.button_immediate_uninstall()
env.cr.commit()
EOF
```

Expected: sin traceback en la salida; el proceso termina limpio.

- [ ] **Step 2: Reiniciar el servidor principal**

Run: `docker restart fortuna-odoo-1`

Expected: el contenedor reinicia y vuelve a responder en `http://localhost:8069`.

- [ ] **Step 3: Confirmar en el navegador**

Abrir una Orden de venta cualquiera (Ventas → cualquier cotización/pedido) en `http://localhost:8069`. Confirmar que solo aparece el botón **"Descuento"** cerca de las líneas — sin "Código de cupón" ni "Recompensa". No hay commit de código para este task (es un cambio de estado de la base de datos, no del repo).

---

### Task 2: Reescribir el wizard de descuento general para escribir `discount` por línea

**Files:**
- Modify: `addons/distribuidora_ventas/wizards/factura_descuento_wizard.py`
- Modify: `addons/distribuidora_ventas/tests/test_factura_descuento_wizard.py`

**Interfaces:**
- Consumes: nada nuevo — sigue siendo el mismo modelo `distribuidora.factura.descuento.wizard` ya registrado en `views/factura_descuento_wizard_views.xml` y `security/ir.model.access.csv` (sin cambios en esos archivos).
- Produces: `action_aplicar(self)` ahora escribe `discount` (Float, 0-100) en cada línea de producto de `move_id` en vez de crear una línea nueva. `move_id` y `porcentaje` (con su `@api.constrains` `_check_porcentaje`) no cambian de nombre ni de comportamiento — Task 5 (verificación manual) depende de que el botón siga llamando a este mismo método.

- [ ] **Step 1: Actualizar el test que verifica el comportamiento nuevo**

En `addons/distribuidora_ventas/tests/test_factura_descuento_wizard.py`, reemplazar el método `test_applies_percentage_discount_with_correct_taxes` completo (líneas 31-46 del archivo actual) por:

```python
    def test_applies_percentage_discount_with_correct_taxes(self):
        self.assertEqual(self.move.amount_untaxed, 2000.0)
        wizard = self.env['distribuidora.factura.descuento.wizard'].create({
            'move_id': self.move.id,
            'porcentaje': 10.0,
        })
        wizard.action_aplicar()

        product_lines = self.move.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        self.assertEqual(len(product_lines), 1)
        self.assertEqual(product_lines.discount, 10.0)
        self.assertAlmostEqual(self.move.amount_untaxed, 1800.0)
        self.assertAlmostEqual(self.move.amount_tax, 1800.0 * self.tax.amount / 100)
        self.assertAlmostEqual(self.move.amount_total, self.move.amount_untaxed + self.move.amount_tax)
```

No tocar `test_rejects_percentage_over_100`, `test_rejects_zero_percentage` ni `test_move_id_defaults_from_active_id_context` — siguen igual, no dependen de `action_aplicar`.

- [ ] **Step 2: Correr los tests para confirmar que el test actualizado falla**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /distribuidora_ventas:TestFacturaDescuentoWizard --stop-after-init --http-port=8169 -u distribuidora_ventas`

Expected: FAIL en `test_applies_percentage_discount_with_correct_taxes` — `product_lines.discount` es `0.0`, no `10.0` (el wizard todavía crea una línea nueva en vez de escribir en la existente).

- [ ] **Step 3: Reescribir el wizard**

Reemplazar el contenido completo de `addons/distribuidora_ventas/wizards/factura_descuento_wizard.py` por:

```python
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FacturaDescuentoWizard(models.TransientModel):
    _name = 'distribuidora.factura.descuento.wizard'
    _description = "Descuento general para facturas de cliente"

    move_id = fields.Many2one(
        'account.move', required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    porcentaje = fields.Float(string="Porcentaje de descuento", required=True)

    @api.constrains('porcentaje')
    def _check_porcentaje(self):
        for wizard in self:
            if not 0 < wizard.porcentaje <= 100:
                raise ValidationError(_(
                    "El porcentaje de descuento debe ser mayor a 0 y menor o igual a 100."
                ))

    def action_aplicar(self):
        self.ensure_one()
        product_lines = self.move_id.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        product_lines.write({'discount': self.porcentaje})
```

Esto elimina `_get_discount_product()` y toda referencia a `company.sale_discount_product_id` — ya no se necesita ningún producto de descuento.

- [ ] **Step 4: Correr toda la suite de `distribuidora_ventas` para confirmar que pasa**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /distribuidora_ventas --stop-after-init --http-port=8169 -u distribuidora_ventas`

Expected: PASS — `0 failed, 0 error(s)` en toda la suite del módulo, incluyendo `TestFacturaDescuentoWizard` (4 tests: el actualizado + los 3 que no cambiaron) y `TestFacturaDescuentoWizardView` (2 tests, sin cambios de código pero deben seguir en verde porque la vista/acción del wizard no se tocó) además de todos los demás tests del módulo que ya pasaban antes de este cambio.

- [ ] **Step 5: Commit**

```bash
git add addons/distribuidora_ventas/wizards/factura_descuento_wizard.py addons/distribuidora_ventas/tests/test_factura_descuento_wizard.py
git commit -m "fix(distribuidora_ventas): aplicar descuento general por linea en vez de linea de producto sin CABYS"
```

---

### Task 3: Confirmar el nombre del campo de descuento en la API de CRLibre

**Files:** ninguno (investigación contra el sandbox local, sin cambios de código todavía — el resultado de este task determina qué rama de código escribe Task 4).

**Interfaces:**
- Consumes: `client.gen_xml_fe(params)` de `l10n_cr.fe.crlibre.client` (`addons/l10n_cr_fe_crlibre/models/crlibre_client.py:84-88`) — este método solo genera el XML localmente contra el contenedor `crlibre-app` (`l10n_cr_fe.api_url` = `http://host.docker.internal:8080`), **no envía nada a Hacienda real** ni consume ningún consecutivo — se puede llamar repetidas veces sin efectos secundarios.
- Produces: la decisión de qué clave usar en el `detalle` dict de `_l10n_cr_fe_build_detalles()` (Task 4).

- [ ] **Step 1: Armar un payload de prueba con un campo de descuento adivinado y generar el XML**

Run (nota: `-i` es una bandera de `docker exec` para pipear stdin, no de `odoo shell`):

```bash
MSYS_NO_PATHCONV=1 docker exec -i fortuna-odoo-1 odoo shell -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --http-port=8169 --no-http <<'EOF'
import json

config = env['l10n_cr.fe.config'].search([], limit=1)
client = env['l10n_cr.fe.crlibre.client']

detalles = [{
    'codigoCABYS': '0111101000000',
    'cantidad': 2,
    'unidadMedida': 'Unid',
    'detalle': 'Producto prueba descuento',
    'precioUnitario': 1000.0,
    'montoTotal': 2000.0,
    'subTotal': 1800.0,
    'baseImponible': 1800.0,
    'impuestoAsumidoEmisorFabrica': 0,
    'impuestoNeto': 234.0,
    'montoTotalLinea': 2034.0,
    'montoDescuento': 200.0,
    'impuesto': [{'codigo': '01', 'codigoTarifa': '08', 'tarifa': 13, 'monto': 234.0}],
}]
medios_pago = [{'tipoMedioPago': '01', 'totalMedioPago': 2034.0}]
params = {
    'clave': '50625072300000000000' + '1' * 30,
    'proveedor_sistemas': config.identification_number,
    'codigo_actividad_emisor': config.economic_activity_code,
    'consecutivo': '00100001010000000001',
    'fecha_emision': '2026-08-10T10:00:00-06:00',
    'emisor_nombre': config.legal_name,
    'emisor_tipo_identif': config.identification_type,
    'emisor_num_identif': config.identification_number,
    'emisor_provincia': config.province,
    'emisor_canton': config.canton,
    'emisor_distrito': config.district,
    'emisor_otras_senas': config.address_detail,
    'emisor_email': config.email,
    'condicion_venta': '01',
    'medios_pago': json.dumps(medios_pago),
    'cod_moneda': 'CRC',
    'tipo_cambio': '1',
    'detalles': json.dumps(detalles),
    'receptor_nombre': 'Cliente Prueba',
    'receptor_tipo_identif': '01',
    'receptor_num_identif': '102340567',
    'total_merc_gravada': 1800.0,
    'total_merc_exenta': 0,
    'total_gravados': 1800.0,
    'total_exento': 0,
    'total_ventas': 1800.0,
    'total_ventas_neta': 1800.0,
    'totalDesgloseImpuesto': json.dumps([{'Codigo': '01', 'CodigoTarifaIVA': '08', 'TotalMontoImpuesto': 234.0}]),
    'total_impuestos': 234.0,
    'total_comprobante': 2034.0,
}
xml = client.gen_xml_fe(params)
print("=====XML RESULT START=====")
print(xml)
print("=====XML RESULT END=====")
env.cr.rollback()
EOF
```

Expected: el script imprime un bloque XML entre los marcadores. Buscar dentro de ese XML (`Ctrl+F` en la salida) las etiquetas `<MontoDescuento>`, `<Descuento>` o similares dentro de `<LineaDetalle>`.

- [ ] **Step 2: Registrar el hallazgo**

Dos resultados posibles, cada uno determina qué código escribe la Task 4:

- **Si el XML trae `<MontoDescuento>200.00</MontoDescuento>` (o similar) dentro de la línea de detalle correspondiente:** la clave `montoDescuento` es correcta. Task 4 usa la rama "campo confirmado".
- **Si el XML NO trae ningún rastro de descuento en esa línea (el campo fue ignorado silenciosamente) o la llamada devuelve error:** la clave `montoDescuento` no es la que espera esta API. Task 4 usa la rama "campo no confirmado" (deja un TODO explícito en el código, sin adivinar otro nombre).

No hay commit en este task — es solo investigación que informa la Task 4.

---

### Task 4: Incluir el descuento por línea en `_l10n_cr_fe_build_detalles`

**Files:**
- Modify: `addons/l10n_cr_fe_crlibre/models/account_move.py:175-211` (método `_l10n_cr_fe_build_detalles`)
- Test: `addons/l10n_cr_fe_crlibre/tests/test_account_move_mapping.py`

**Interfaces:**
- Consumes: resultado de la Task 3 (qué rama de código/test aplica — elegir UNA de las dos ramas de abajo, completa, no mezclar pasos de ambas).
- Produces: `_l10n_cr_fe_build_detalles()` sigue devolviendo `list[dict]` con las mismas claves que antes; cuando una línea tiene `discount > 0`, el dict de esa línea también refleja el descuento (rama A: clave `montoDescuento` nueva; rama B: sin clave nueva, solo un comentario `TODO` documentando el hueco).

`addons/l10n_cr_fe_crlibre/tests/test_account_move_mapping.py` ya tiene un helper `_create_invoice_with_tax(tax_amount)` (líneas 105-128 actuales) que crea una factura de 1 unidad a ₡1000 con un producto con CABYS y un impuesto de venta de la tarifa indicada, sobre `self.partner` (`Cliente Demo`, definido en `setUp`). Se reutiliza en el test de este task.

#### Rama A — la Task 3 confirmó `montoDescuento` como la clave correcta

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de la clase `TestAccountMoveMapping`:

```python
    def test_build_detalles_incluye_monto_descuento_por_linea(self):
        invoice = self._create_invoice_with_tax(13)
        invoice.invoice_line_ids.write({'discount': 10.0})

        detalle = invoice._l10n_cr_fe_build_detalles()[0]

        self.assertEqual(detalle['montoTotal'], 1000.0)
        self.assertEqual(detalle['subTotal'], 900.0)
        self.assertEqual(detalle['montoDescuento'], 100.0)

    def test_build_detalles_sin_descuento_no_incluye_monto_descuento(self):
        invoice = self._create_invoice_with_tax(13)
        detalle = invoice._l10n_cr_fe_build_detalles()[0]
        self.assertNotIn('montoDescuento', detalle)
```

- [ ] **Step 2: Correr los tests para confirmar que el primero falla**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestAccountMoveMapping --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL en `test_build_detalles_incluye_monto_descuento_por_linea` — `KeyError: 'montoDescuento'` (la clave no existe todavía). `test_build_detalles_sin_descuento_no_incluye_monto_descuento` ya pasa (no hay ninguna clave `montoDescuento` en ningún lado todavía).

- [ ] **Step 3: Modificar `_l10n_cr_fe_build_detalles`**

En `addons/l10n_cr_fe_crlibre/models/account_move.py`, dentro del `for line in ...` de `_l10n_cr_fe_build_detalles` (después de construir el dict `detalle`, antes del `if impuesto_neto:` — ver líneas 184-197 actuales), agregar:

```python
            monto_bruto = line.price_unit * line.quantity
            monto_descuento = monto_bruto - subtotal
            if monto_descuento:
                detalle['montoDescuento'] = monto_descuento
```

#### Rama B — la Task 3 NO pudo confirmar la clave

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de la clase `TestAccountMoveMapping`:

```python
    def test_build_detalles_con_descuento_mantiene_montototal_bruto(self):
        invoice = self._create_invoice_with_tax(13)
        invoice.invoice_line_ids.write({'discount': 10.0})

        detalle = invoice._l10n_cr_fe_build_detalles()[0]

        # Documenta el estado conocido y aceptado de este hueco: montoTotal
        # sigue siendo el bruto y no hay ninguna clave que explique la
        # diferencia con subTotal todavia (ver TODO en el metodo). Este test
        # existe para que, el dia que se agregue el campo real, falle aqui y
        # obligue a actualizarlo en vez de quedar desactualizado en silencio.
        self.assertEqual(detalle['montoTotal'], 1000.0)
        self.assertEqual(detalle['subTotal'], 900.0)
        self.assertNotIn('montoDescuento', detalle)
```

- [ ] **Step 2: Correr el test para confirmar que pasa sin cambios de código todavía**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestAccountMoveMapping --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — este test documenta el estado actual (que ya es así hoy, sin ningún cambio). No hay ciclo rojo/verde tradicional en esta rama porque no se está agregando comportamiento nuevo, solo dejando constancia explícita del hueco conocido.

- [ ] **Step 3: Dejar el `TODO` explícito en `_l10n_cr_fe_build_detalles`**

En `addons/l10n_cr_fe_crlibre/models/account_move.py`, dentro del `for line in ...` de `_l10n_cr_fe_build_detalles` (después de construir el dict `detalle`, antes del `if impuesto_neto:` — ver líneas 184-197 actuales), agregar:

```python
            monto_bruto = line.price_unit * line.quantity
            monto_descuento = monto_bruto - subtotal
            if monto_descuento:
                # TODO: confirmar contra la API de CRLibre el nombre exacto del
                # campo de descuento por linea antes de enviarlo — se probo
                # 'montoDescuento' contra el sandbox local (docs/superpowers/
                # plans/2026-08-10-descuento-general-facturacion-hacienda.md,
                # Task 3) y no se pudo confirmar que la API lo reconozca.
                # Por ahora NO se envia el campo para evitar mandar un dato
                # incorrecto sin detectarlo; montoTotal/subTotal quedan
                # descuadrados en el XML resultante cuando hay descuento.
                pass
```

#### Ambas ramas convergen aquí

- [ ] **Step 4: Correr los tests de la clase para confirmar que todos pasan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestAccountMoveMapping --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)` en todos los tests de `TestAccountMoveMapping` (los existentes + los 2 nuevos de la rama elegida).

- [ ] **Step 5: Correr la suite completa de `l10n_cr_fe_crlibre` para confirmar que no se rompió nada**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)` (208 tests ya existentes + los nuevos de la rama elegida en el Step 1: 2 más si se siguió la Rama A, 1 más si se siguió la Rama B).

- [ ] **Step 6: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/models/account_move.py addons/l10n_cr_fe_crlibre/tests/test_account_move_mapping.py
git commit -m "fix(l10n_cr_fe_crlibre): incluir descuento por linea en el detalle enviado a Hacienda"
```

---

### Task 5: Instalar `distribuidora_ventas` y verificación manual end-to-end

**Files:** ninguno (solo verificación en el navegador).

- [ ] **Step 1: Actualizar módulos y reiniciar el servidor**

Run:
```bash
MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo -i distribuidora_ventas --stop-after-init --http-port=8169
docker restart fortuna-odoo-1
```

Expected: ambos comandos terminan sin errores; el contenedor vuelve a responder en `http://localhost:8069`.

- [ ] **Step 2: Aplicar un descuento general en una factura de prueba**

En `http://localhost:8069`: crear una factura de cliente (Contabilidad/Facturación → Clientes → Facturas → Nuevo) con 2-3 líneas de producto con impuesto, dejarla en borrador. Confirmar que aparece el botón "Descuento general". Hacer clic, poner `10`, "Aplicar".

Verificar: cada línea de producto original queda con la columna "Desc.%" en `10.00` (sin ninguna línea nueva agregada), y el total baja el 10% correspondiente sobre el neto.

- [ ] **Step 3: Confirmar que el botón desaparece al validar**

Confirmar/publicar la factura → verificar que el botón "Descuento general" ya no aparece.

- [ ] **Step 4: Confirmar Preventas sin cambios**

Abrir una Orden de venta → confirmar que el botón "Descuento" nativo sigue funcionando igual que siempre (modo "On All Order Lines" también deja `discount` por línea, para contraste).

- [ ] **Step 5: Si hay credenciales de sandbox de Hacienda configuradas, probar el envío real con una factura descontada**

Solo si `l10n_cr.fe.config` ya tiene certificado/credenciales cargadas en esta base (confirmar antes de intentar — si no las hay, omitir este paso sin bloquear el resto del plan): crear una factura con un producto que tenga CABYS, aplicar un descuento general del 10%, y correr el flujo de envío a Hacienda ya existente en el formulario. Confirmar que no aparece el error "no tiene código CABYS configurado" (el que rompía con el mecanismo viejo) y que el envío se comporta igual que una factura sin descuento.
