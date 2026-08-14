# Actividades económicas por cliente

- **Fecha:** 2026-08-14
- **Estado:** Aprobado (diseño)
- **Alcance:** Cada cliente (`res.partner`) puede tener registradas varias actividades económicas ante Hacienda, buscadas y agregadas desde la API pública de Hacienda usando su cédula. Al crear una Orden de venta o una Factura, se elige a cuál de esas actividades corresponde el documento, y ese código se envía a Hacienda dentro del XML del comprobante.

---

## 1. Contexto

Se detectó que `l10n_cr_fe_crlibre` hoy solo envía a Hacienda la actividad económica del **emisor** (la propia empresa, desde `l10n_cr.fe.config.economic_activity_code`) — nunca la del **receptor** (el cliente). Se confirmó contra el XSD oficial v4.4 (`https://www.hacienda.go.cr/docs/FacturaElectronica_V4.4.xsd.xml`, descargado en vivo) que sí existe un campo `CodigoActividadReceptor` (opcional, `minOccurs="0"`, string de exactamente 6 dígitos, al mismo nivel que `CodigoActividadEmisor`), documentado como necesario *"en caso de ser requerido para un crédito o un gasto deducible"*.

Un mismo cliente (ej. un hotel) puede tener varias actividades económicas registradas ante Hacienda simultáneamente (restaurante, bar, hospedaje, etc.), y cada venta puede corresponder a una actividad distinta.

Se investigó y confirmó en vivo que Hacienda expone una API pública para consultar las actividades económicas **registradas de un contribuyente específico por su cédula**: `https://api.hacienda.go.cr/fe/ae?identificacion=<cédula>`, sin autenticación. Devuelve, entre otros datos, un arreglo `actividades` con `codigo`, `descripcion`, `tipo` y `estado` (`"A"` = activa) por cada actividad registrada. La documentación oficial de esta API (`https://api.hacienda.go.cr/docs`) confirma que **no existe** una forma de buscar/listar el catálogo completo de actividades por texto — solo consulta por cédula de un contribuyente puntual. Límites documentados: ráfaga 20 req/s (máx. 100 en 5s), sostenido 10 req/s (máx. 1200 en 2 min), bloqueo de IP de 10 min si se excede — sin impacto para el uso manual de este wizard.

Precedente directo en este mismo módulo: el buscador de CABYS en producto (`docs/superpowers/plans/2026-08-10-buscador-cabys-producto.md`), que sigue el mismo patrón — un `AbstractModel` cliente HTTP que llama directo a una API pública de Hacienda, y un wizard `TransientModel` que muestra resultados y los aplica solo con confirmación explícita del usuario.

## 2. Objetivo y definición de "hecho"

1. Desde la ficha de cualquier cliente, se puede buscar (por la cédula ya guardada) y agregar una o varias de sus actividades económicas reales registradas en Hacienda.
2. Al crear una Orden de venta o Factura de cliente y elegir el cliente, aparece un selector con las actividades económicas de ese cliente. Es obligatorio elegir una si el cliente tiene al menos una registrada; si no tiene ninguna, se puede dejar vacío.
3. La actividad elegida en la Orden de venta se copia automáticamente a la Factura generada desde ella.
4. El XML que se envía a Hacienda incluye `codigo_actividad_receptor` cuando hay una actividad elegida en el documento.

**Éxito =** agregar 2 actividades reales a un cliente de prueba (usando su cédula contra el sandbox), crear una factura para ese cliente, confirmar que el selector obliga a elegir una, y verificar — contra el sandbox real de CRLibre, no solo con un test unitario — que el XML generado trae `<CodigoActividadReceptor>` con el código correcto.

## 3. Diseño

### 3.1 Modelo `l10n_cr.fe.partner.activity`

Nuevo modelo persistente (`addons/l10n_cr_fe_crlibre/models/partner_activity.py`):
- `partner_id` (Many2one `res.partner`, requerido, `ondelete='cascade'`)
- `code` (Char, requerido, validado como 6 dígitos)
- `description` (Char, requerido)
- Restricción: no se puede repetir el mismo `code` en el mismo `partner_id`.
- Seguridad: acceso completo (`1,1,1,1`) para `account.group_account_invoice`, mismo grupo que ya usan `l10n_cr.fe.cabys.wizard` y el resto de modelos de este módulo ligados al flujo de venta/facturación (ver `security/ir.model.access.csv` actual).

`res.partner` (`res_partner.py`, ya existe en este módulo) gana `l10n_cr_fe_activity_ids` (One2many a lo anterior, `inverse_name='partner_id'`). Sin necesidad de migración: todo cliente existente o nuevo simplemente empieza con la lista vacía hasta que alguien agregue actividades.

### 3.2 Cliente HTTP `l10n_cr.fe.activity.client`

Nuevo `AbstractModel` (`addons/l10n_cr_fe_crlibre/models/partner_activity_client.py`), mismo patrón que `cabys_client.py`:
- Método `buscar(cedula)` → `GET https://api.hacienda.go.cr/fe/ae` con `params={'identificacion': cedula}`.
- Devuelve `list[dict]` con `codigo`, `descripcion` — solo las entradas con `estado == 'A'` (activas; se descartan las inactivas, no tiene sentido facturar contra una actividad que el cliente ya no tiene vigente).
- Lanza `ActivityApiError` (excepción propia del archivo, mismo patrón que `CabysApiError`) en cualquier fallo: cédula vacía/formato inválido, error de red, HTTP≠200, JSON inválido, o respuesta sin la clave `actividades`.

### 3.3 Wizard de búsqueda y selección

`l10n_cr.fe.partner.activity.wizard` (`TransientModel`, `addons/l10n_cr_fe_crlibre/wizards/partner_activity_wizard.py`):
- `partner_id` (Many2one, requerido, default desde contexto `default_partner_id`).
- `searched` (Boolean), `result_ids` (One2many a `l10n_cr.fe.partner.activity.wizard.line`).
- `action_buscar()`: si `partner_id.vat` está vacío, `UserError` pidiendo completar la cédula primero. Si no, llama `client.buscar(partner_id.vat)`; en `ActivityApiError`, re-lanza como `UserError`.

`l10n_cr.fe.partner.activity.wizard.line` (`TransientModel`):
- `wizard_id`, `codigo`, `descripcion` (readonly).
- `ya_agregada` (Boolean, computado): `True` si ya existe un `l10n_cr.fe.partner.activity` con ese código para `wizard_id.partner_id`.
- `action_agregar()`: crea el `l10n_cr.fe.partner.activity` (si `ya_agregada` ya es `True`, no hace nada — idempotente). **A diferencia del wizard de CABYS, este NO cierra el wizard al confirmar** — devuelve la misma acción para mantenerlo abierto, permitiendo agregar varias actividades en una sola búsqueda (caso del hotel con restaurante+bar+hospedaje). El botón se deshabilita/oculta en las filas ya agregadas.

Vista en la ficha de cliente: sección "Actividades Económicas ante Hacienda" con la lista de `l10n_cr_fe_activity_ids` (Código/Descripción, solo lectura) y un botón "Agregar Actividad Económica" que abre el wizard — igual al mockup mostrado.

Seguridad: acceso completo (`1,1,1,1`) para `account.group_account_invoice` en ambos modelos del wizard, mismo grupo ya usado por `l10n_cr.fe.cabys.wizard` / `.wizard.line`.

### 3.4 Selector en `sale.order` y `account.move`

Ambos modelos ganan `l10n_cr_fe_activity_id` (Many2one a `l10n_cr.fe.partner.activity`, dominio `[('partner_id', '=', partner_id)]`, se limpia si cambia el cliente).

- `sale.order`: archivo nuevo `addons/l10n_cr_fe_crlibre/models/sale_order.py` (no existe todavía en este módulo). Validación en `action_confirm()`: si `partner_id.l10n_cr_fe_activity_ids` no está vacío y `l10n_cr_fe_activity_id` no está seteado, `UserError` explicando que este cliente tiene actividades registradas y debe elegirse una.
- `account.move` (ya existe `account_move.py`): mismo campo, misma validación en `action_post()` (antes del flujo de envío a Hacienda, junto a las validaciones ya existentes ahí — ver `_l10n_cr_fe_build_genxml_params`, que ya valida que el receptor tenga cédula).
- Override de `sale.order._prepare_invoice()` para copiar `l10n_cr_fe_activity_id` al diccionario de valores de la factura nueva — así la Factura generada desde la Orden hereda la actividad elegida (editable después).

### 3.5 Envío a Hacienda

En `_l10n_cr_fe_build_genxml_params()` (`account_move.py`), junto a donde ya se arma `codigo_actividad_emisor`: si `self.l10n_cr_fe_activity_id`, agregar `params['codigo_actividad_receptor'] = self.l10n_cr_fe_activity_id.code`. Si no hay actividad elegida, no se agrega la clave — el campo es opcional en el XSD (`minOccurs="0"`), así que omitirlo no rompe nada.

**Punto a verificar empíricamente en el plan de implementación, no asumido aquí:** `codigo_actividad_receptor` es el nombre de parámetro más probable para CRLibre por el patrón ya establecido (`codigo_actividad_emisor` → `<CodigoActividadEmisor>`, confirmado y funcionando en producción hoy), pero antes de darlo por bueno debe probarse en vivo contra el sandbox local de CRLibre (`client.gen_xml_fe`, mismo método usado en `docs/superpowers/plans/2026-08-10-descuento-general-facturacion-hacienda.md` Task 3) para confirmar que el XML resultante efectivamente trae `<CodigoActividadReceptor>` con el valor correcto — no repetir el error de asumir un nombre de campo sin probarlo (ver ese mismo plan, hallazgo de la revisión final).

## 4. Fuera de alcance

- Importar o mantener un catálogo completo de actividades económicas de Costa Rica — la API pública de Hacienda no lo permite (solo consulta por cédula de un contribuyente puntual, confirmado contra `https://api.hacienda.go.cr/docs`).
- Sincronizar/actualizar automáticamente actividades ya agregadas si cambian de estado en Hacienda (ej. una actividad se desactiva después de agregada) — quedan tal como se agregaron hasta que alguien las gestione manualmente.
- Actividad económica por línea de producto/servicio — el campo `CodigoActividadReceptor` del XSD es a nivel de documento completo, no por línea.
- Cambios al flujo de Mensaje Receptor (MR, facturas de proveedor) — este diseño es solo para el receptor de nuestras propias facturas de venta (`out_invoice`/`out_refund` vía `sale.order`/`account.move`).

## 5. Estrategia de pruebas

- `l10n_cr.fe.activity.client`: tests con `unittest.mock.patch` sobre `requests.get`, cubriendo éxito, filtrado de inactivas, cédula vacía, error de red, HTTP≠200, JSON inválido, respuesta sin `actividades` — mismo patrón que `test_cabys_client.py`.
- Wizard: búsqueda llena `result_ids`, agregar una línea crea el registro en el cliente, agregar una ya agregada es idempotente, el wizard permite agregar varias sin cerrarse, error claro si el cliente no tiene cédula.
- `sale.order`/`account.move`: confirmar/postear sin actividad elegida cuando el cliente tiene actividades registradas debe fallar; cuando no tiene ninguna, debe pasar; el campo se limpia si cambia el cliente.
- Copia orden→factura: crear una orden con actividad elegida, generar la factura, confirmar que trae la misma actividad.
- `_l10n_cr_fe_build_genxml_params`: con actividad elegida, el dict trae `codigo_actividad_receptor`; sin actividad, no trae la clave.
- Verificación manual contra el sandbox real (como en el plan de descuento general): confirmar que `<CodigoActividadReceptor>` aparece en el XML real generado por CRLibre con el valor correcto, antes de dar la Task del XML por terminada.
