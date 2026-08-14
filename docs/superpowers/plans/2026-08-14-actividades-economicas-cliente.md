# Actividades económicas por cliente — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada cliente puede tener registradas varias actividades económicas ante Hacienda (buscadas por su cédula contra la API pública de Hacienda), elegir a cuál corresponde cada Orden de venta/Factura, y que ese código viaje en el XML que se envía a Hacienda.

**Architecture:** Un `AbstractModel` cliente HTTP (`l10n_cr.fe.activity.client`) consulta `https://api.hacienda.go.cr/fe/ae?identificacion=<cédula>` (misma técnica que el buscador de CABYS ya existente). Un modelo persistente (`l10n_cr.fe.partner.activity`) guarda las actividades elegidas por cliente, poblado por un wizard `TransientModel` que — a diferencia del wizard de CABYS — no se cierra al confirmar, para poder agregar varias actividades en una sola búsqueda. `sale.order` y `account.move` ganan un selector de actividad filtrado por cliente; en la orden de venta el campo bloquea la confirmación si falta (no toca Hacienda), en la factura sigue el patrón ya establecido en este módulo de "nunca bloquear la contabilización por datos de Hacienda incompletos" (error suave + reintentar).

**Tech Stack:** Odoo 19 (Python 3.10–3.14) en Docker (`fortuna-odoo-1`/`fortuna-db-1`/`crlibre-app`), `odoo.tests.common.TransactionCase`, `unittest.mock`.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-14-actividades-economicas-cliente-design.md`.
- Imports ordenados: future → stdlib → third-party → odoo → odoo.addons (lo aplica `ruff`).
- Tests con `@tagged('post_install', '-at_install')`, `TransactionCase`, mocking con `unittest.mock.patch` — mismas convenciones que el resto de `l10n_cr_fe_crlibre` (ver `tests/test_cabys_client.py`, `wizards/cabys_wizard.py`, `tests/test_cabys_wizard.py` como plantilla directa).
- Seguridad de los 3 modelos nuevos: `account.group_account_invoice`, acceso completo (`1,1,1,1`) — mismo grupo que ya usan `l10n_cr.fe.cabys.wizard`/`.wizard.line` (spec §3.1, §3.3).
- La API pública de Hacienda (`/fe/ae`) solo acepta `identificacion` — no existe forma de buscar/listar el catálogo completo por texto (spec §1, confirmado contra `https://api.hacienda.go.cr/docs`).
- `CodigoActividadReceptor` en el XSD v4.4 es opcional (`minOccurs="0"`), string de exactamente 6 dígitos, al mismo nivel que `CodigoActividadEmisor` — confirmado descargando `https://www.hacienda.go.cr/docs/FacturaElectronica_V4.4.xsd.xml` en vivo (spec §1, §3.5).
- En `account.move`, ninguna validación relacionada a Hacienda debe bloquear `action_post()` — el patrón establecido (cédula faltante, CABYS faltante, certificado faltante) es: la factura se contabiliza igual, el envío a Hacienda queda en `l10n_cr_fe_state='error'` con mensaje en el chatter, reintentable con el botón "Reintentar envío FE" ya existente. Confirmado con tests existentes (`tests/test_action_post_fe.py::test_action_post_does_not_block_when_product_missing_cabys`). La validación de actividad económica en `account.move` debe seguir este mismo patrón (decisión explícita del usuario, no aplica en `sale.order` porque ahí no hay envío a Hacienda).
- **Comandos de esta sesión, verificados y en uso:**
  - Tests: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:<Clase> --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre` (puerto 8069 ocupado por el proceso principal, por eso `--http-port=8169`; `MSYS_NO_PATHCONV=1` obligatorio o Git Bash rompe el tag `/modulo:Clase`).
  - Tras cualquier `-u` en ejecución aparte, `docker restart fortuna-odoo-1` para que el proceso que sirve `localhost:8069` recargue el registro.
  - `odoo shell` para scripts puntuales: `docker exec -i fortuna-odoo-1 odoo shell -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --http-port=8169 --no-http <<'EOF' ... EOF` (el `-i` es de `docker exec`, no de `odoo shell`).
  - El modelo del cliente CRLibre se llama `l10n_cr.fe.client` (no `l10n_cr.fe.crlibre.client` — nombre fácil de adivinar mal, ya pasó en esta sesión).
  - `addons/l10n_cr_fe_crlibre/tests/__init__.py`, `wizards/__init__.py` y `models/__init__.py` necesitan los imports nuevos agregados explícitamente en cada task que crea un archivo — a `test_cabys_client.py` se le olvidó una vez y sus tests nunca corrieron hasta corregirlo.

---

### Task 1: Cliente HTTP del catálogo de actividades económicas

**Files:**
- Create: `addons/l10n_cr_fe_crlibre/models/partner_activity_client.py`
- Modify: `addons/l10n_cr_fe_crlibre/models/__init__.py`
- Create: `addons/l10n_cr_fe_crlibre/tests/test_partner_activity_client.py`
- Modify: `addons/l10n_cr_fe_crlibre/tests/__init__.py`

**Interfaces:**
- Produces: `ActivityApiError(Exception)`; modelo `l10n_cr.fe.activity.client` (`AbstractModel`) con método `buscar(self, cedula)` → `list[dict]`, cada dict con claves `codigo` (str) y `descripcion` (str). Solo incluye actividades con `estado == 'A'`. Lanza `ActivityApiError` en cualquier fallo (cédula vacía, red, HTTP≠200, JSON inválido, respuesta sin clave `actividades`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `addons/l10n_cr_fe_crlibre/tests/test_partner_activity_client.py`:

```python
from unittest.mock import MagicMock, patch

import requests

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client import ActivityApiError


def _mock_response(status_code=200, json_data=None, raise_json=False):
    resp = MagicMock()
    resp.status_code = status_code
    if raise_json:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_data
    return resp


@tagged('post_install', '-at_install')
class TestPartnerActivityClient(TransactionCase):

    def setUp(self):
        super().setUp()
        self.client = self.env['l10n_cr.fe.activity.client']

    def test_buscar_usa_parametro_identificacion(self):
        resp = _mock_response(json_data={
            'nombre': 'ARAR SOCIEDAD ANONIMA',
            'actividades': [
                {'estado': 'A', 'tipo': 'P', 'codigo': '960113',
                 'descripcion': 'PERSONA JURIDICA LEGALMENTE CONSTITUIDAS'},
            ],
        })
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp) as mock_get:
            resultados = self.client.buscar('3101042624')
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.kwargs['params'], {'identificacion': '3101042624'})
        self.assertEqual(resultados, [
            {'codigo': '960113', 'descripcion': 'PERSONA JURIDICA LEGALMENTE CONSTITUIDAS'},
        ])

    def test_buscar_filtra_actividades_inactivas(self):
        resp = _mock_response(json_data={
            'actividades': [
                {'estado': 'A', 'codigo': '561001', 'descripcion': 'Restaurantes'},
                {'estado': 'I', 'codigo': '563001', 'descripcion': 'Bares (inactiva)'},
            ],
        })
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            resultados = self.client.buscar('102340567')
        self.assertEqual(resultados, [{'codigo': '561001', 'descripcion': 'Restaurantes'}])

    def test_buscar_cedula_vacia_lanza_error_sin_llamar_api(self):
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get') as mock_get:
            with self.assertRaises(ActivityApiError):
                self.client.buscar('')
        mock_get.assert_not_called()

    def test_buscar_timeout_lanza_activity_api_error(self):
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    side_effect=requests.exceptions.Timeout()):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('102340567')

    def test_buscar_http_error_lanza_activity_api_error(self):
        resp = _mock_response(status_code=500)
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('102340567')

    def test_buscar_json_invalido_lanza_activity_api_error(self):
        resp = _mock_response(raise_json=True)
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('102340567')

    def test_buscar_respuesta_sin_actividades_lanza_activity_api_error(self):
        resp = _mock_response(json_data={'code': 400, 'status': 'Bad Request'})
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            with self.assertRaises(ActivityApiError):
                self.client.buscar('000000000')

    def test_buscar_sin_actividades_activas_devuelve_lista_vacia(self):
        resp = _mock_response(json_data={'actividades': []})
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.requests.get',
                    return_value=resp):
            resultados = self.client.buscar('102340567')
        self.assertEqual(resultados, [])
```

```python
# addons/l10n_cr_fe_crlibre/tests/__init__.py — agregar junto a los demás imports:
from . import test_partner_activity_client
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestPartnerActivityClient --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL — `ModuleNotFoundError`/`ImportError` porque `partner_activity_client.py` no existe todavía.

- [ ] **Step 3: Implementar `models/partner_activity_client.py`**

```python
import requests

from odoo import models

ACTIVITY_URL = 'https://api.hacienda.go.cr/fe/ae'
TIMEOUT = 15


class ActivityApiError(Exception):
    """Error al consultar las actividades económicas registradas de un contribuyente en Hacienda."""


class ActivityClient(models.AbstractModel):
    _name = 'l10n_cr.fe.activity.client'
    _description = 'Cliente HTTP para actividades económicas de Hacienda (por cédula)'

    def buscar(self, cedula):
        cedula = (cedula or '').strip()
        if not cedula:
            raise ActivityApiError("Debe indicar la cédula del cliente para buscar sus actividades económicas.")
        try:
            resp = requests.get(ACTIVITY_URL, params={'identificacion': cedula}, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise ActivityApiError("No se pudo conectar con la API de Hacienda: %s" % exc)
        if resp.status_code != 200:
            raise ActivityApiError("La API de Hacienda respondió HTTP %s" % resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            raise ActivityApiError("La API de Hacienda devolvió una respuesta no-JSON.")
        return self._normalizar(data)

    def _normalizar(self, data):
        if not isinstance(data, dict) or 'actividades' not in data:
            raise ActivityApiError("Respuesta inesperada de la API de Hacienda: %s" % data)
        resultados = []
        for item in data['actividades'] or []:
            if not isinstance(item, dict) or not item.get('codigo') or item.get('estado') != 'A':
                continue
            resultados.append({
                'codigo': item['codigo'],
                'descripcion': item.get('descripcion', ''),
            })
        return resultados
```

Modificar `addons/l10n_cr_fe_crlibre/models/__init__.py` agregando la línea de import junto a `cabys_client` (orden alfabético relativo a las existentes):

```python
from . import cabys_client
from . import crlibre_client
from . import fe_config
from . import partner_activity_client
from . import product_template
from . import res_partner
from . import account_move
from . import proveedor_email
```

- [ ] **Step 4: Ejecutar los tests y verificar que pasan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestPartnerActivityClient --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — 7 tests en verde.

- [ ] **Step 5: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/models/partner_activity_client.py addons/l10n_cr_fe_crlibre/models/__init__.py addons/l10n_cr_fe_crlibre/tests/test_partner_activity_client.py addons/l10n_cr_fe_crlibre/tests/__init__.py
git commit -m "feat(l10n_cr_fe_crlibre): agregar cliente HTTP de actividades económicas de Hacienda"
```

---

### Task 2: Modelo de actividades económicas por cliente

**Files:**
- Create: `addons/l10n_cr_fe_crlibre/models/partner_activity.py`
- Modify: `addons/l10n_cr_fe_crlibre/models/res_partner.py`
- Modify: `addons/l10n_cr_fe_crlibre/models/__init__.py`
- Create: `addons/l10n_cr_fe_crlibre/tests/test_partner_activity.py`
- Modify: `addons/l10n_cr_fe_crlibre/tests/__init__.py`

**Interfaces:**
- Consumes: nada de Task 1 todavía.
- Produces: modelo `l10n_cr.fe.partner.activity` (`partner_id` Many2one requerido `ondelete='cascade'`, `code` Char 6 dígitos requerido, `description` Char requerido); `res.partner.l10n_cr_fe_activity_ids` (One2many). Las tasks siguientes dependen de estos nombres exactos.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `addons/l10n_cr_fe_crlibre/tests/test_partner_activity.py`:

```python
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPartnerActivity(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Hotel Demo', 'vat': '3101042624'})

    def test_create_activity_shows_in_partner_activity_ids(self):
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        self.assertEqual(len(self.partner.l10n_cr_fe_activity_ids), 1)
        self.assertEqual(self.partner.l10n_cr_fe_activity_ids.code, '561001')

    def test_partner_can_have_multiple_activities(self):
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '563001', 'description': 'Bares',
        })
        self.assertEqual(len(self.partner.l10n_cr_fe_activity_ids), 2)

    def test_invalid_code_length_raises(self):
        with self.assertRaises(ValidationError):
            self.env['l10n_cr.fe.partner.activity'].create({
                'partner_id': self.partner.id, 'code': '123', 'description': 'x',
            })

    def test_invalid_code_non_digit_raises(self):
        with self.assertRaises(ValidationError):
            self.env['l10n_cr.fe.partner.activity'].create({
                'partner_id': self.partner.id, 'code': 'ABCDEF', 'description': 'x',
            })

    def test_duplicate_code_same_partner_raises(self):
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        with self.assertRaises(Exception):
            self.env['l10n_cr.fe.partner.activity'].create({
                'partner_id': self.partner.id, 'code': '561001', 'description': 'Duplicado',
            })

    def test_same_code_different_partners_allowed(self):
        other_partner = self.env['res.partner'].create({'name': 'Otro Cliente'})
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': other_partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        self.assertTrue(activity.id)
```

```python
# addons/l10n_cr_fe_crlibre/tests/__init__.py — agregar junto a los demás imports:
from . import test_partner_activity
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestPartnerActivity --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL — `KeyError: 'l10n_cr.fe.partner.activity'` (el modelo no existe todavía).

- [ ] **Step 3: Implementar `models/partner_activity.py`**

```python
import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

ACTIVITY_CODE_RE = re.compile(r'^\d{6}$')


class L10nCrFePartnerActivity(models.Model):
    _name = 'l10n_cr.fe.partner.activity'
    _description = "Actividad económica registrada ante Hacienda de un cliente"

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    code = fields.Char(string="Código", required=True)
    description = fields.Char(string="Descripción", required=True)

    _code_partner_uniq = models.Constraint(
        'UNIQUE (partner_id, code)',
        "Esta actividad económica ya está registrada para este cliente.",
    )

    @api.constrains('code')
    def _check_code(self):
        for activity in self:
            if not ACTIVITY_CODE_RE.match(activity.code or ''):
                raise ValidationError(
                    _("El código de actividad económica debe tener exactamente 6 dígitos."))
```

Modificar `addons/l10n_cr_fe_crlibre/models/res_partner.py` (contenido completo):

```python
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_cr_fe_identification_type = fields.Selection(
        selection=[('01', 'Física'), ('02', 'Jurídica'), ('03', 'DIMEX'), ('04', 'NITE')],
        string="Tipo de identificación FE", default='01',
        help="Tipo de identificación del cliente para Factura Electrónica de Hacienda.")
    l10n_cr_fe_activity_ids = fields.One2many(
        'l10n_cr.fe.partner.activity', 'partner_id', string="Actividades económicas ante Hacienda")
```

Modificar `addons/l10n_cr_fe_crlibre/models/__init__.py` agregando `partner_activity` (debe cargar antes que `res_partner`, que ya lo referencia vía One2many — Odoo resuelve esto sin problema por nombre de modelo, pero se mantiene el orden alfabético relativo ya usado):

```python
from . import cabys_client
from . import crlibre_client
from . import fe_config
from . import partner_activity
from . import partner_activity_client
from . import product_template
from . import res_partner
from . import account_move
from . import proveedor_email
```

- [ ] **Step 4: Ejecutar los tests y verificar que pasan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestPartnerActivity --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — 6 tests en verde.

- [ ] **Step 5: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/models/partner_activity.py addons/l10n_cr_fe_crlibre/models/res_partner.py addons/l10n_cr_fe_crlibre/models/__init__.py addons/l10n_cr_fe_crlibre/tests/test_partner_activity.py addons/l10n_cr_fe_crlibre/tests/__init__.py
git commit -m "feat(l10n_cr_fe_crlibre): agregar modelo de actividades económicas por cliente"
```

---

### Task 3: Wizard de búsqueda y selección múltiple de actividades

**Files:**
- Create: `addons/l10n_cr_fe_crlibre/wizards/partner_activity_wizard.py`
- Modify: `addons/l10n_cr_fe_crlibre/wizards/__init__.py`
- Create: `addons/l10n_cr_fe_crlibre/tests/test_partner_activity_wizard.py`
- Modify: `addons/l10n_cr_fe_crlibre/tests/__init__.py`

**Interfaces:**
- Consumes: `l10n_cr.fe.activity.client.buscar(cedula)` (Task 1); `l10n_cr.fe.partner.activity` y `res.partner.l10n_cr_fe_activity_ids` (Task 2).
- Produces: modelos `l10n_cr.fe.partner.activity.wizard` (`partner_id`, `searched`, `result_ids`) y `l10n_cr.fe.partner.activity.wizard.line` (`wizard_id`, `codigo`, `descripcion`, `ya_agregada`); métodos `action_buscar(self)` en el wizard y `action_agregar(self)` en la línea. Las vistas de Task 4 referencian estos nombres exactos.

**Nota de diseño (spec §3.3):** a diferencia de `l10n_cr.fe.cabys.wizard.line.action_usar()`, que cierra el wizard con `ir.actions.act_window_close`, `action_agregar()` **no cierra el wizard** — devuelve la misma acción para dejarlo abierto y poder agregar varias actividades en una sola búsqueda.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `addons/l10n_cr_fe_crlibre/tests/test_partner_activity_wizard.py`:

```python
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPartnerActivityWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Hotel Demo', 'vat': '3101042624'})

    def _patch_buscar(self, resultados):
        return patch(
            'odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.ActivityClient.buscar',
            return_value=resultados)

    def test_action_buscar_llena_result_ids(self):
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].create({'partner_id': self.partner.id})
        resultados = [
            {'codigo': '561001', 'descripcion': 'Restaurantes y servicios móviles'},
            {'codigo': '563001', 'descripcion': 'Bares, cantinas y tabernas'},
        ]
        with self._patch_buscar(resultados):
            wizard.action_buscar()
        self.assertTrue(wizard.searched)
        self.assertEqual(len(wizard.result_ids), 2)
        self.assertEqual(wizard.result_ids[0].codigo, '561001')

    def test_action_buscar_sin_cedula_lanza_usererror(self):
        from odoo.exceptions import UserError

        from odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client import ActivityApiError

        partner_sin_cedula = self.env['res.partner'].create({'name': 'Sin cédula'})
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].create({'partner_id': partner_sin_cedula.id})
        with patch(
            'odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client.ActivityClient.buscar',
            side_effect=ActivityApiError("Debe indicar la cédula del cliente para buscar sus actividades económicas."),
        ):
            with self.assertRaises(UserError):
                wizard.action_buscar()

    def test_action_agregar_crea_actividad_en_cliente(self):
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].create({'partner_id': self.partner.id})
        line = self.env['l10n_cr.fe.partner.activity.wizard.line'].create({
            'wizard_id': wizard.id, 'codigo': '561001', 'descripcion': 'Restaurantes',
        })
        result = line.action_agregar()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'l10n_cr.fe.partner.activity.wizard')
        self.assertEqual(len(self.partner.l10n_cr_fe_activity_ids), 1)
        self.assertEqual(self.partner.l10n_cr_fe_activity_ids.code, '561001')

    def test_action_agregar_no_cierra_el_wizard(self):
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].create({'partner_id': self.partner.id})
        line = self.env['l10n_cr.fe.partner.activity.wizard.line'].create({
            'wizard_id': wizard.id, 'codigo': '561001', 'descripcion': 'Restaurantes',
        })
        result = line.action_agregar()
        self.assertNotEqual(result.get('type'), 'ir.actions.act_window_close')

    def test_action_agregar_permite_varias_en_una_sesion(self):
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].create({'partner_id': self.partner.id})
        line1 = self.env['l10n_cr.fe.partner.activity.wizard.line'].create({
            'wizard_id': wizard.id, 'codigo': '561001', 'descripcion': 'Restaurantes',
        })
        line2 = self.env['l10n_cr.fe.partner.activity.wizard.line'].create({
            'wizard_id': wizard.id, 'codigo': '563001', 'descripcion': 'Bares',
        })
        line1.action_agregar()
        line2.action_agregar()
        self.assertEqual(len(self.partner.l10n_cr_fe_activity_ids), 2)

    def test_action_agregar_ya_agregada_es_idempotente(self):
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].create({'partner_id': self.partner.id})
        line = self.env['l10n_cr.fe.partner.activity.wizard.line'].create({
            'wizard_id': wizard.id, 'codigo': '561001', 'descripcion': 'Restaurantes',
        })
        self.assertTrue(line.ya_agregada)
        line.action_agregar()
        self.assertEqual(len(self.partner.l10n_cr_fe_activity_ids), 1)

    def test_ya_agregada_false_para_actividad_nueva(self):
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].create({'partner_id': self.partner.id})
        line = self.env['l10n_cr.fe.partner.activity.wizard.line'].create({
            'wizard_id': wizard.id, 'codigo': '999999', 'descripcion': 'Nueva',
        })
        self.assertFalse(line.ya_agregada)
```

```python
# addons/l10n_cr_fe_crlibre/tests/__init__.py — agregar junto a los demás imports:
from . import test_partner_activity_wizard
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestPartnerActivityWizard --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL — `l10n_cr.fe.partner.activity.wizard` no existe como modelo todavía.

- [ ] **Step 3: Implementar `wizards/partner_activity_wizard.py`**

```python
from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_cr_fe_crlibre.models.partner_activity_client import ActivityApiError


class L10nCrFePartnerActivityWizard(models.TransientModel):
    _name = 'l10n_cr.fe.partner.activity.wizard'
    _description = "Buscador de actividades económicas (Hacienda)"

    partner_id = fields.Many2one('res.partner', required=True, readonly=True)
    searched = fields.Boolean(default=False)
    result_ids = fields.One2many('l10n_cr.fe.partner.activity.wizard.line', 'wizard_id')

    def action_buscar(self):
        self.ensure_one()
        client = self.env['l10n_cr.fe.activity.client']
        try:
            resultados = client.buscar(self.partner_id.vat)
        except ActivityApiError as exc:
            raise UserError(str(exc))
        self.result_ids = [(5, 0, 0)] + [(0, 0, {
            'codigo': r['codigo'], 'descripcion': r['descripcion'],
        }) for r in resultados]
        self.searched = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cr.fe.partner.activity.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class L10nCrFePartnerActivityWizardLine(models.TransientModel):
    _name = 'l10n_cr.fe.partner.activity.wizard.line'
    _description = "Resultado de búsqueda de actividad económica"

    wizard_id = fields.Many2one('l10n_cr.fe.partner.activity.wizard', required=True, ondelete='cascade')
    codigo = fields.Char(readonly=True)
    descripcion = fields.Char(readonly=True)
    ya_agregada = fields.Boolean(compute='_compute_ya_agregada')

    @api.depends('codigo', 'wizard_id.partner_id.l10n_cr_fe_activity_ids.code')
    def _compute_ya_agregada(self):
        for line in self:
            line.ya_agregada = bool(
                line.codigo and line.codigo in line.wizard_id.partner_id.l10n_cr_fe_activity_ids.mapped('code'))

    def action_agregar(self):
        self.ensure_one()
        if not self.ya_agregada:
            self.env['l10n_cr.fe.partner.activity'].create({
                'partner_id': self.wizard_id.partner_id.id,
                'code': self.codigo,
                'description': self.descripcion,
            })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_cr.fe.partner.activity.wizard',
            'view_mode': 'form',
            'res_id': self.wizard_id.id,
            'target': 'new',
        }
```

Modificar `addons/l10n_cr_fe_crlibre/wizards/__init__.py`:

```python
from . import account_move_reversal
from . import proveedor_upload
from . import mr_motivo_wizard
from . import account_debit_note
from . import cabys_wizard
from . import partner_activity_wizard
```

- [ ] **Step 4: Ejecutar los tests y verificar que pasan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestPartnerActivityWizard --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — 7 tests en verde.

- [ ] **Step 5: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/wizards/partner_activity_wizard.py addons/l10n_cr_fe_crlibre/wizards/__init__.py addons/l10n_cr_fe_crlibre/tests/test_partner_activity_wizard.py addons/l10n_cr_fe_crlibre/tests/__init__.py
git commit -m "feat(l10n_cr_fe_crlibre): agregar wizard de búsqueda y selección de actividades económicas"
```

---

### Task 4: Vistas, seguridad y manifiesto

**Files:**
- Create: `addons/l10n_cr_fe_crlibre/views/partner_activity_wizard_views.xml`
- Modify: `addons/l10n_cr_fe_crlibre/views/res_partner_views.xml`
- Modify: `addons/l10n_cr_fe_crlibre/security/ir.model.access.csv`
- Modify: `addons/l10n_cr_fe_crlibre/__manifest__.py`
- Test: `addons/l10n_cr_fe_crlibre/tests/test_partner_activity_wizard.py` (agrega un caso de integración)

**Interfaces:**
- Consumes: `l10n_cr.fe.partner.activity.wizard`/`.wizard.line` (Task 3).
- Produces: módulo instalable de punta a punta desde la interfaz (botón en ficha de cliente → wizard → agregar varias → cerrar → aparecen en la ficha).

- [ ] **Step 1: Escribir el test de integración que falla**

Agregar al final de la clase `TestPartnerActivityWizard` en `addons/l10n_cr_fe_crlibre/tests/test_partner_activity_wizard.py`:

```python
    def test_flujo_completo_boton_cliente_hasta_varias_actividades(self):
        action = self.env.ref('l10n_cr_fe_crlibre.action_l10n_cr_fe_partner_activity_wizard')
        wizard = self.env['l10n_cr.fe.partner.activity.wizard'].with_context(
            default_partner_id=self.partner.id).create({})
        self.assertEqual(wizard.partner_id, self.partner)
        with self._patch_buscar([
            {'codigo': '561001', 'descripcion': 'Restaurantes y servicios móviles'},
            {'codigo': '563001', 'descripcion': 'Bares, cantinas y tabernas'},
        ]):
            wizard.action_buscar()
        wizard.result_ids[0].action_agregar()
        wizard.result_ids[1].action_agregar()
        self.assertEqual(len(self.partner.l10n_cr_fe_activity_ids), 2)
        self.assertEqual(action['res_model'], 'l10n_cr.fe.partner.activity.wizard')
```

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestPartnerActivityWizard --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL — `ValueError: External ID not found: l10n_cr_fe_crlibre.action_l10n_cr_fe_partner_activity_wizard` (la acción todavía no existe).

- [ ] **Step 3: Crear la vista y acción del wizard**

Crear `addons/l10n_cr_fe_crlibre/views/partner_activity_wizard_views.xml`:

```xml
<odoo>
    <record id="view_l10n_cr_fe_partner_activity_wizard_form" model="ir.ui.view">
        <field name="name">l10n_cr.fe.partner.activity.wizard.form</field>
        <field name="model">l10n_cr.fe.partner.activity.wizard</field>
        <field name="arch" type="xml">
            <form string="Buscar actividades económicas">
                <field name="partner_id" invisible="1"/>
                <field name="searched" invisible="1"/>
                <button name="action_buscar" string="Buscar" type="object"
                        class="btn-primary" icon="fa-search"/>
                <field name="result_ids" invisible="not searched">
                    <list create="false" delete="false">
                        <field name="codigo"/>
                        <field name="descripcion"/>
                        <field name="ya_agregada" column_invisible="1"/>
                        <button name="action_agregar" type="object"
                                string="Agregar" class="btn-link" icon="fa-plus"
                                invisible="ya_agregada"/>
                    </list>
                </field>
                <p invisible="not searched or result_ids">
                    No se encontraron actividades económicas activas para este cliente.
                </p>
                <footer>
                    <button string="Cerrar" special="cancel" class="btn-secondary"/>
                </footer>
            </form>
        </field>
    </record>

    <record id="action_l10n_cr_fe_partner_activity_wizard" model="ir.actions.act_window">
        <field name="name">Agregar Actividad Económica</field>
        <field name="res_model">l10n_cr.fe.partner.activity.wizard</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
    </record>
</odoo>
```

- [ ] **Step 4: Agregar la sección en la ficha del cliente**

Reemplazar el contenido de `addons/l10n_cr_fe_crlibre/views/res_partner_views.xml`:

```xml
<odoo>
    <record id="view_partner_form_l10n_cr_fe" model="ir.ui.view">
        <field name="name">res.partner.form.l10n.cr.fe</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='vat']" position="after">
                <field name="l10n_cr_fe_identification_type"
                       invisible="not vat"/>
            </xpath>
            <notebook position="inside">
                <page string="Actividades Económicas ante Hacienda" name="l10n_cr_fe_activities">
                    <field name="l10n_cr_fe_activity_ids">
                        <list create="false" delete="false" editable="false">
                            <field name="code" string="Código"/>
                            <field name="description" string="Descripción"/>
                        </list>
                    </field>
                    <button name="%(action_l10n_cr_fe_partner_activity_wizard)d"
                            type="action" string="Agregar Actividad Económica"
                            class="btn-link" icon="fa-plus"
                            context="{'default_partner_id': id}"/>
                </page>
            </notebook>
        </field>
    </record>
</odoo>
```

- [ ] **Step 5: Registrar acceso de seguridad**

Agregar tres filas al final de `addons/l10n_cr_fe_crlibre/security/ir.model.access.csv`:

```csv
access_l10n_cr_fe_partner_activity,l10n_cr.fe.partner.activity,model_l10n_cr_fe_partner_activity,account.group_account_invoice,1,1,1,1
access_l10n_cr_fe_partner_activity_wizard,l10n_cr.fe.partner.activity.wizard,model_l10n_cr_fe_partner_activity_wizard,account.group_account_invoice,1,1,1,1
access_l10n_cr_fe_partner_activity_wizard_line,l10n_cr.fe.partner.activity.wizard.line,model_l10n_cr_fe_partner_activity_wizard_line,account.group_account_invoice,1,1,1,1
```

- [ ] **Step 6: Registrar la vista nueva en el manifiesto**

En `addons/l10n_cr_fe_crlibre/__manifest__.py`, agregar `'views/partner_activity_wizard_views.xml'` a la lista `data`, junto a `views/cabys_wizard_views.xml`:

```python
    'data': [
        'data/system_params.xml',
        'security/l10n_cr_fe_security.xml',
        'security/ir.model.access.csv',
        'views/fe_config_views.xml',
        'views/product_template_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/account_move_reversal_views.xml',
        'views/account_debit_note_views.xml',
        'views/proveedor_upload_views.xml',
        'views/mr_motivo_wizard_views.xml',
        'views/cabys_wizard_views.xml',
        'views/partner_activity_wizard_views.xml',
        'views/proveedor_email_views.xml',
        'data/mail_template.xml',
    ],
```

- [ ] **Step 7: Actualizar el módulo e instalar las vistas**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo -u l10n_cr_fe_crlibre --stop-after-init --http-port=8169`

Expected: termina sin errores (confirma que el XML de las vistas es válido y el CSV de permisos carga bien).

- [ ] **Step 8: Ejecutar toda la suite del módulo**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)` en toda la suite (todos los tests previos del módulo + los nuevos de Tasks 1-3).

- [ ] **Step 9: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/views/partner_activity_wizard_views.xml addons/l10n_cr_fe_crlibre/views/res_partner_views.xml addons/l10n_cr_fe_crlibre/security/ir.model.access.csv addons/l10n_cr_fe_crlibre/__manifest__.py addons/l10n_cr_fe_crlibre/tests/test_partner_activity_wizard.py
git commit -m "feat(l10n_cr_fe_crlibre): cablear vistas, seguridad y manifest del buscador de actividades económicas"
```

---

### Task 5: Selector de actividad económica en Orden de venta

**Files:**
- Create: `addons/l10n_cr_fe_crlibre/models/sale_order.py`
- Modify: `addons/l10n_cr_fe_crlibre/models/__init__.py`
- Create: `addons/l10n_cr_fe_crlibre/views/sale_order_views.xml`
- Modify: `addons/l10n_cr_fe_crlibre/__manifest__.py`
- Create: `addons/l10n_cr_fe_crlibre/tests/test_sale_order_activity.py`
- Modify: `addons/l10n_cr_fe_crlibre/tests/__init__.py`

**Interfaces:**
- Consumes: `l10n_cr.fe.partner.activity` (Task 2).
- Produces: `sale.order.l10n_cr_fe_activity_id` (Many2one, dominio por `partner_id`). Task 7 depende de este nombre de campo exacto para copiarlo a la factura.

**Nota importante (Global Constraints):** a diferencia de `account.move`, aquí SÍ corresponde bloquear de verdad — `sale.order` no toca Hacienda, así que un `UserError` en `action_confirm()` simplemente impide confirmar la cotización hasta elegir la actividad, sin ningún efecto secundario en envíos.

`l10n_cr_fe_crlibre` no depende de `sale` todavía (`depends = ['account', 'l10n_cr', 'account_debit_note']`) — este task lo agrega.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `addons/l10n_cr_fe_crlibre/tests/test_sale_order_activity.py`:

```python
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleOrderActivity(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Hotel Demo', 'vat': '3101042624'})
        self.product = self.env['product.product'].create({'name': 'Habitación', 'list_price': 50000.0})

    def _create_order(self, partner=None):
        return self.env['sale.order'].create({
            'partner_id': (partner or self.partner).id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 1})],
        })

    def test_confirm_without_activity_raises_when_partner_has_activities(self):
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        order = self._create_order()
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_confirm_with_activity_succeeds(self):
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        order = self._create_order()
        order.l10n_cr_fe_activity_id = activity.id
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_confirm_without_activity_succeeds_when_partner_has_none(self):
        order = self._create_order()
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_activity_id_clears_when_partner_changes(self):
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        other_partner = self.env['res.partner'].create({'name': 'Otro Cliente'})
        order = self._create_order()
        order.l10n_cr_fe_activity_id = activity.id
        order.partner_id = other_partner.id
        order._onchange_partner_id_l10n_cr_fe_activity()
        self.assertFalse(order.l10n_cr_fe_activity_id)
```

```python
# addons/l10n_cr_fe_crlibre/tests/__init__.py — agregar junto a los demás imports:
from . import test_sale_order_activity
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestSaleOrderActivity --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL — `AttributeError: 'sale.order' object has no attribute 'l10n_cr_fe_activity_id'` (y el módulo `sale_order.py` no existe).

- [ ] **Step 3: Agregar `sale` como dependencia**

En `addons/l10n_cr_fe_crlibre/__manifest__.py`, cambiar:

```python
    'depends': ['account', 'l10n_cr', 'account_debit_note'],
```

por:

```python
    'depends': ['account', 'l10n_cr', 'account_debit_note', 'sale'],
```

- [ ] **Step 4: Implementar `models/sale_order.py`**

```python
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    l10n_cr_fe_activity_id = fields.Many2one(
        'l10n_cr.fe.partner.activity', string="Actividad económica",
        domain="[('partner_id', '=', partner_id)]")

    @api.onchange('partner_id')
    def _onchange_partner_id_l10n_cr_fe_activity(self):
        if self.l10n_cr_fe_activity_id and self.l10n_cr_fe_activity_id.partner_id != self.partner_id:
            self.l10n_cr_fe_activity_id = False

    def action_confirm(self):
        for order in self:
            if order.partner_id.l10n_cr_fe_activity_ids and not order.l10n_cr_fe_activity_id:
                raise UserError(_(
                    "El cliente '%s' tiene actividades económicas registradas ante Hacienda. "
                    "Debe elegir a cuál corresponde esta orden antes de confirmarla."
                ) % order.partner_id.name)
        return super().action_confirm()
```

Modificar `addons/l10n_cr_fe_crlibre/models/__init__.py`:

```python
from . import cabys_client
from . import crlibre_client
from . import fe_config
from . import partner_activity
from . import partner_activity_client
from . import product_template
from . import res_partner
from . import account_move
from . import sale_order
from . import proveedor_email
```

- [ ] **Step 5: Agregar el campo a la vista de Orden de venta**

Crear `addons/l10n_cr_fe_crlibre/views/sale_order_views.xml`:

```xml
<odoo>
    <record id="view_order_form_l10n_cr_fe" model="ir.ui.view">
        <field name="name">sale.order.form.l10n.cr.fe</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='partner_id']" position="after">
                <field name="l10n_cr_fe_activity_id" string="Actividad económica"
                       invisible="not partner_id"/>
            </xpath>
        </field>
    </record>
</odoo>
```

- [ ] **Step 6: Registrar la vista en el manifiesto**

En `addons/l10n_cr_fe_crlibre/__manifest__.py`, agregar `'views/sale_order_views.xml'` a `data`, junto a `views/product_template_views.xml`:

```python
    'data': [
        'data/system_params.xml',
        'security/l10n_cr_fe_security.xml',
        'security/ir.model.access.csv',
        'views/fe_config_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/account_move_reversal_views.xml',
        'views/account_debit_note_views.xml',
        'views/proveedor_upload_views.xml',
        'views/mr_motivo_wizard_views.xml',
        'views/cabys_wizard_views.xml',
        'views/partner_activity_wizard_views.xml',
        'views/proveedor_email_views.xml',
        'data/mail_template.xml',
    ],
```

- [ ] **Step 7: Actualizar el módulo y ejecutar los tests**

Run:
```bash
MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo -u l10n_cr_fe_crlibre --stop-after-init --http-port=8169
MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestSaleOrderActivity --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre
```

Expected: el primer comando termina sin errores (confirma que agregar `sale` como dependencia y el XML de la vista son válidos); el segundo, PASS — 4 tests en verde.

- [ ] **Step 8: Ejecutar toda la suite del módulo**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)`. Agregar `sale` como dependencia carga módulos adicionales; confirmar que nada existente se rompió.

- [ ] **Step 9: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/models/sale_order.py addons/l10n_cr_fe_crlibre/models/__init__.py addons/l10n_cr_fe_crlibre/views/sale_order_views.xml addons/l10n_cr_fe_crlibre/__manifest__.py addons/l10n_cr_fe_crlibre/tests/test_sale_order_activity.py addons/l10n_cr_fe_crlibre/tests/__init__.py
git commit -m "feat(l10n_cr_fe_crlibre): agregar selector obligatorio de actividad económica en orden de venta"
```

---

### Task 6: Selector de actividad económica en Factura de cliente

**Files:**
- Modify: `addons/l10n_cr_fe_crlibre/models/account_move.py`
- Modify: `addons/l10n_cr_fe_crlibre/views/account_move_views.xml`
- Test: `addons/l10n_cr_fe_crlibre/tests/test_action_post_fe.py`

**Interfaces:**
- Consumes: `l10n_cr.fe.partner.activity` (Task 2).
- Produces: `account.move.l10n_cr_fe_activity_id` (Many2one, dominio por `partner_id`). Task 7 y Task 9 dependen de este nombre de campo exacto.

**Nota importante (Global Constraints):** la validación va **dentro** del bloque `try:` de `_l10n_cr_fe_generate_and_send()` (líneas 500-567 actuales, junto a `client = self.env['l10n_cr.fe.client']`), NO antes — así, si falta, sigue el mismo patrón que cédula/CABYS/certificado: no bloquea `action_post()`, solo dificulta que el envío a Hacienda tenga éxito, y el error queda registrado en `l10n_cr_fe_state='error'` + chatter, reintentable con "Reintentar envío FE".

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de la clase `TestActionPostFe` en `addons/l10n_cr_fe_crlibre/tests/test_action_post_fe.py`:

```python
    def test_action_post_does_not_block_when_activity_required_but_missing(self):
        partner = self.env['res.partner'].create({'name': 'Hotel Demo', 'vat': '3101042624'})
        self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        product = self.env['product.product'].create({
            'name': 'Habitación', 'l10n_cr_fe_cabys': '0111101000000'})
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'company_id': self.company.id,
            'partner_id': partner.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id, 'quantity': 1, 'price_unit': 50000.0,
                'name': 'Habitación', 'tax_ids': [(6, 0, [])],
            })],
        })
        with patch('odoo.addons.l10n_cr_fe_crlibre.models.crlibre_client.CrlibreFeClient.get_clave',
                   return_value={'clave': '5' * 50, 'consecutivo': '0' * 20}):
            invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.l10n_cr_fe_state, 'error')
        self.assertTrue(any(
            'actividad económica' in (msg.body or '')
            for msg in invoice.message_ids))

    def test_action_post_with_activity_chosen_succeeds(self):
        partner = self.env['res.partner'].create({'name': 'Hotel Demo', 'vat': '3101042624'})
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        product = self.env['product.product'].create({
            'name': 'Habitación', 'l10n_cr_fe_cabys': '0111101000000'})
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'company_id': self.company.id,
            'partner_id': partner.id,
            'l10n_cr_fe_activity_id': activity.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id, 'quantity': 1, 'price_unit': 50000.0,
                'name': 'Habitación', 'tax_ids': [(6, 0, [])],
            })],
        })
        patchers = self._patch_full_success()
        for p in patchers:
            p.start()
        try:
            invoice.action_post()
        finally:
            for p in patchers:
                p.stop()
        self.assertEqual(invoice.l10n_cr_fe_state, 'enviado')
```

- [ ] **Step 2: Ejecutar los tests y verificar que fallan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestActionPostFe --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL en los 2 tests nuevos — `AttributeError: 'account.move' object has no attribute 'l10n_cr_fe_activity_id'` (o `ValueError` al crear el registro con esa clave).

- [ ] **Step 3: Agregar el campo y la validación en `account_move.py`**

Buscar la clase `AccountMove` en `addons/l10n_cr_fe_crlibre/models/account_move.py` y agregar el campo nuevo junto a los demás campos `l10n_cr_fe_*` ya declarados ahí (cualquier punto dentro de la clase, siguiendo el patrón existente):

```python
    l10n_cr_fe_activity_id = fields.Many2one(
        'l10n_cr.fe.partner.activity', string="Actividad económica",
        domain="[('partner_id', '=', partner_id)]")
```

En el método `_l10n_cr_fe_generate_and_send()`, el bloque `try:` empieza en la línea 501 actual (justo después de `client = self.env['l10n_cr.fe.client']`, línea 500) y su primera línea actual dentro del bloque es `if self.move_type == 'out_refund':` (línea 502). El `if` nuevo se agrega como primera línea dentro del `try:`, antes de esa — así queda protegido por el mismo `except (CrlibreApiError, UserError) as exc:` de la línea 568 actual, que es lo que lo convierte en `l10n_cr_fe_state='error'` + mensaje en el chatter sin bloquear `action_post()` (igual que ya hacen las validaciones de cédula/CABYS/certificado):

```python
        client = self.env['l10n_cr.fe.client']
        try:
            if self.partner_id.l10n_cr_fe_activity_ids and not self.l10n_cr_fe_activity_id:
                raise UserError(_(
                    "El cliente '%s' tiene actividades económicas registradas ante Hacienda. "
                    "Debe elegir a cuál corresponde este comprobante."
                ) % self.partner_id.name)
            if self.move_type == 'out_refund':
```

(el resto del bloque `try:` sigue exactamente igual que hoy — solo se agrega el `if` nuevo al principio).

- [ ] **Step 4: Agregar el campo a la vista de factura**

En `addons/l10n_cr_fe_crlibre/views/account_move_views.xml`, dentro del `<group>` de la página "Factura Electrónica CR" (que ya lista `l10n_cr_fe_clave`, `l10n_cr_fe_consecutivo`, etc.), agregar como primer campo del grupo:

```xml
                    <group>
                        <field name="l10n_cr_fe_activity_id" string="Actividad económica"
                               invisible="move_type not in ('out_invoice', 'out_refund')"/>
                        <field name="l10n_cr_fe_clave"/>
```

(el resto del `<group>` queda exactamente igual que hoy — solo se agrega esta línea nueva antes de `l10n_cr_fe_clave`).

- [ ] **Step 5: Ejecutar los tests y verificar que pasan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestActionPostFe --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — todos los tests de `TestActionPostFe` (los ya existentes + los 2 nuevos).

- [ ] **Step 6: Ejecutar toda la suite del módulo**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)`.

- [ ] **Step 7: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/models/account_move.py addons/l10n_cr_fe_crlibre/views/account_move_views.xml addons/l10n_cr_fe_crlibre/tests/test_action_post_fe.py
git commit -m "feat(l10n_cr_fe_crlibre): agregar selector de actividad económica en factura (error suave, no bloquea)"
```

---

### Task 7: Copiar actividad económica de la Orden de venta a la Factura

**Files:**
- Modify: `addons/l10n_cr_fe_crlibre/models/sale_order.py`
- Create: `addons/l10n_cr_fe_crlibre/tests/test_sale_order_invoice_activity.py`
- Modify: `addons/l10n_cr_fe_crlibre/tests/__init__.py`

**Interfaces:**
- Consumes: `sale.order.l10n_cr_fe_activity_id` (Task 5), `account.move.l10n_cr_fe_activity_id` (Task 6).
- Produces: la factura generada desde una orden confirmada trae copiada la misma actividad económica.

- [ ] **Step 1: Escribir el test que falla**

Crear `addons/l10n_cr_fe_crlibre/tests/test_sale_order_invoice_activity.py`:

```python
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleOrderInvoiceActivity(TransactionCase):

    def test_invoice_created_from_order_copies_activity(self):
        partner = self.env['res.partner'].create({'name': 'Hotel Demo', 'vat': '3101042624'})
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        product = self.env['product.product'].create({
            'name': 'Habitación', 'invoice_policy': 'order', 'l10n_cr_fe_cabys': '0111101000000'})
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'l10n_cr_fe_activity_id': activity.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1})],
        })
        order.action_confirm()
        invoice = order._create_invoices()
        self.assertEqual(invoice.l10n_cr_fe_activity_id, activity)
```

```python
# addons/l10n_cr_fe_crlibre/tests/__init__.py — agregar junto a los demás imports:
from . import test_sale_order_invoice_activity
```

- [ ] **Step 2: Ejecutar el test y verificar que falla**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestSaleOrderInvoiceActivity --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL — `self.assertEqual(invoice.l10n_cr_fe_activity_id, activity)` falla porque `invoice.l10n_cr_fe_activity_id` está vacío (todavía no se copia).

- [ ] **Step 3: Agregar el override de `_prepare_invoice`**

En `addons/l10n_cr_fe_crlibre/models/sale_order.py`, agregar el método al final de la clase `SaleOrder` (después de `action_confirm`):

```python
    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        if self.l10n_cr_fe_activity_id:
            values['l10n_cr_fe_activity_id'] = self.l10n_cr_fe_activity_id.id
        return values
```

- [ ] **Step 4: Ejecutar el test y verificar que pasa**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestSaleOrderInvoiceActivity --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS.

- [ ] **Step 5: Ejecutar toda la suite del módulo**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)`.

- [ ] **Step 6: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/models/sale_order.py addons/l10n_cr_fe_crlibre/tests/test_sale_order_invoice_activity.py addons/l10n_cr_fe_crlibre/tests/__init__.py
git commit -m "feat(l10n_cr_fe_crlibre): copiar actividad económica de la orden de venta a la factura"
```

---

### Task 8: Confirmar el nombre del campo en la API de CRLibre

**Files:** ninguno (investigación contra el sandbox local, sin cambios de código todavía — el resultado determina qué rama de código escribe Task 9).

**Interfaces:**
- Consumes: `client.gen_xml_fe(params)` de `l10n_cr.fe.client` (`addons/l10n_cr_fe_crlibre/models/crlibre_client.py`) — solo genera el XML localmente contra el contenedor `crlibre-app` (`l10n_cr_fe.api_url` = `http://host.docker.internal:8080`), **no envía nada a Hacienda real** ni consume ningún consecutivo — se puede llamar repetidas veces sin efectos secundarios. Mismo mecanismo ya usado en `docs/superpowers/plans/2026-08-10-descuento-general-facturacion-hacienda.md` Task 3.
- Produces: la decisión de qué clave usar para `codigo_actividad_receptor` en `_l10n_cr_fe_build_genxml_params()` (Task 9).

- [ ] **Step 1: Armar un payload de prueba con `codigo_actividad_receptor` y generar el XML**

Run (nota: `-i` es una bandera de `docker exec` para pipear stdin, no de `odoo shell`):

```bash
MSYS_NO_PATHCONV=1 docker exec -i fortuna-odoo-1 odoo shell -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --http-port=8169 --no-http <<'EOF'
import json

config = env['l10n_cr.fe.config'].search([], limit=1)
client = env['l10n_cr.fe.client']

detalles = [{
    'codigoCABYS': '0111101000000',
    'cantidad': 1,
    'unidadMedida': 'Unid',
    'detalle': 'Producto prueba actividad receptor',
    'precioUnitario': 1000.0,
    'montoTotal': 1000.0,
    'subTotal': 1000.0,
    'baseImponible': 1000.0,
    'impuestoAsumidoEmisorFabrica': 0,
    'impuestoNeto': 130.0,
    'montoTotalLinea': 1130.0,
    'impuesto': [{'codigo': '01', 'codigoTarifa': '08', 'tarifa': 13, 'monto': 130.0}],
}]
medios_pago = [{'tipoMedioPago': '01', 'totalMedioPago': 1130.0}]
params = {
    'clave': '50625072300000000000' + '2' * 30,
    'proveedor_sistemas': config.identification_number,
    'codigo_actividad_emisor': config.economic_activity_code,
    'consecutivo': '00100001010000000002',
    'fecha_emision': '2026-08-14T10:00:00-06:00',
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
    'receptor_nombre': 'Cliente Prueba Actividad',
    'receptor_tipo_identif': '01',
    'receptor_num_identif': '102340567',
    'codigo_actividad_receptor': '561001',
    'total_merc_gravada': 1000.0,
    'total_merc_exenta': 0,
    'total_gravados': 1000.0,
    'total_exento': 0,
    'total_ventas': 1000.0,
    'total_ventas_neta': 1000.0,
    'totalDesgloseImpuesto': json.dumps([{'Codigo': '01', 'CodigoTarifaIVA': '08', 'TotalMontoImpuesto': 130.0}]),
    'total_impuestos': 130.0,
    'total_comprobante': 1130.0,
}
xml = client.gen_xml_fe(params)
print("=====XML RESULT START=====")
print(xml)
print("=====XML RESULT END=====")
env.cr.rollback()
EOF
```

Expected: el script imprime un bloque XML entre los marcadores. Buscar dentro de ese XML (`Ctrl+F` en la salida) la etiqueta `<CodigoActividadReceptor>`.

- [ ] **Step 2: Registrar el hallazgo**

Dos resultados posibles, cada uno determina qué código escribe la Task 9:

- **Si el XML trae `<CodigoActividadReceptor>561001</CodigoActividadReceptor>`:** la clave `codigo_actividad_receptor` es correcta. Task 9 usa la rama "campo confirmado" (Rama A).
- **Si el XML NO trae esa etiqueta (el campo fue ignorado silenciosamente) o la llamada devuelve error:** la clave no es la que espera esta API. Task 9 usa la rama "campo no confirmado" (Rama B — TODO explícito en el código, sin adivinar otro nombre).

No hay commit en este task — es solo investigación que informa la Task 9.

---

### Task 9: Incluir la actividad económica del receptor en el XML enviado a Hacienda

**Files:**
- Modify: `addons/l10n_cr_fe_crlibre/models/account_move.py:274-332` (método `_l10n_cr_fe_build_genxml_params`)
- Test: `addons/l10n_cr_fe_crlibre/tests/test_account_move_mapping.py`

**Interfaces:**
- Consumes: resultado de la Task 8 (qué rama de código/test aplica — elegir UNA de las dos ramas completa, no mezclar pasos de ambas); `account.move.l10n_cr_fe_activity_id` (Task 6).
- Produces: `_l10n_cr_fe_build_genxml_params()` sigue devolviendo el mismo dict de siempre; cuando el documento tiene `l10n_cr_fe_activity_id`, el dict también trae el código de actividad del receptor (Rama A: clave `codigo_actividad_receptor`; Rama B: sin clave nueva, comentario `TODO`).

#### Rama A — la Task 8 confirmó `codigo_actividad_receptor` como la clave correcta

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de la clase `TestAccountMoveMapping` en `addons/l10n_cr_fe_crlibre/tests/test_account_move_mapping.py`:

```python
    def test_build_genxml_params_incluye_actividad_receptor(self):
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        self.invoice.l10n_cr_fe_activity_id = activity.id
        detalles = self.invoice._l10n_cr_fe_build_detalles()
        params = self.invoice._l10n_cr_fe_build_genxml_params('5' * 50, '0' * 20, detalles)
        self.assertEqual(params['codigo_actividad_receptor'], '561001')

    def test_build_genxml_params_sin_actividad_no_incluye_la_clave(self):
        detalles = self.invoice._l10n_cr_fe_build_detalles()
        params = self.invoice._l10n_cr_fe_build_genxml_params('5' * 50, '0' * 20, detalles)
        self.assertNotIn('codigo_actividad_receptor', params)
```

- [ ] **Step 2: Ejecutar los tests para confirmar que el primero falla**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestAccountMoveMapping --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: FAIL en `test_build_genxml_params_incluye_actividad_receptor` — `KeyError: 'codigo_actividad_receptor'`. `test_build_genxml_params_sin_actividad_no_incluye_la_clave` ya pasa.

- [ ] **Step 3: Modificar `_l10n_cr_fe_build_genxml_params`**

En `addons/l10n_cr_fe_crlibre/models/account_move.py`, dentro del bloque `else:` que arma `receptor_nombre`/`receptor_tipo_identif`/`receptor_num_identif` (líneas 310-313 actuales — el que NO aplica para Tiquete Electrónico), agregar justo después de `params['receptor_num_identif'] = ...`:

```python
        else:
            params['receptor_nombre'] = self.partner_id.name or ''
            params['receptor_tipo_identif'] = self.partner_id.l10n_cr_fe_identification_type or '01'
            params['receptor_num_identif'] = self.partner_id.vat.replace('-', '').strip()
            if self.l10n_cr_fe_activity_id:
                params['codigo_actividad_receptor'] = self.l10n_cr_fe_activity_id.code
```

#### Rama B — la Task 8 NO pudo confirmar la clave

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de la clase `TestAccountMoveMapping`:

```python
    def test_build_genxml_params_con_actividad_no_incluye_clave_no_confirmada(self):
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        self.invoice.l10n_cr_fe_activity_id = activity.id
        detalles = self.invoice._l10n_cr_fe_build_detalles()
        params = self.invoice._l10n_cr_fe_build_genxml_params('5' * 50, '0' * 20, detalles)
        # Documenta el estado conocido y aceptado de este hueco: no se envia
        # ningun campo de actividad del receptor todavia (ver TODO en el
        # metodo). Este test existe para que, el dia que se confirme el
        # nombre real, falle aqui y obligue a actualizarlo.
        self.assertNotIn('codigo_actividad_receptor', params)
```

- [ ] **Step 2: Ejecutar el test para confirmar que pasa sin cambios de código todavía**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestAccountMoveMapping --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — documenta el estado actual, ya así hoy. No hay ciclo rojo/verde tradicional en esta rama porque no se agrega comportamiento nuevo, solo se deja constancia explícita.

- [ ] **Step 3: Dejar el `TODO` explícito en `_l10n_cr_fe_build_genxml_params`**

En `addons/l10n_cr_fe_crlibre/models/account_move.py`, dentro del mismo bloque `else:` (líneas 310-313 actuales), agregar justo después de `params['receptor_num_identif'] = ...`:

```python
        else:
            params['receptor_nombre'] = self.partner_id.name or ''
            params['receptor_tipo_identif'] = self.partner_id.l10n_cr_fe_identification_type or '01'
            params['receptor_num_identif'] = self.partner_id.vat.replace('-', '').strip()
            if self.l10n_cr_fe_activity_id:
                # TODO: confirmar contra la API de CRLibre el nombre exacto del
                # campo de actividad economica del receptor antes de enviarlo —
                # se probo 'codigo_actividad_receptor' contra el sandbox local
                # (docs/superpowers/plans/2026-08-14-actividades-economicas-
                # cliente.md, Task 8) y no se pudo confirmar que la API lo
                # reconozca. Por ahora NO se envia el campo para evitar mandar
                # un dato incorrecto sin detectarlo.
                pass
```

#### Ambas ramas convergen aquí

- [ ] **Step 4: Ejecutar los tests de la clase para confirmar que todos pasan**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre:TestAccountMoveMapping --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)` en todos los tests de `TestAccountMoveMapping` (los existentes + los 2 nuevos de la rama elegida).

- [ ] **Step 5: Ejecutar la suite completa de `l10n_cr_fe_crlibre`**

Run: `MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo --test-enable --test-tags /l10n_cr_fe_crlibre --stop-after-init --http-port=8169 -u l10n_cr_fe_crlibre`

Expected: PASS — `0 failed, 0 error(s)`.

- [ ] **Step 6: Commit**

```bash
git add addons/l10n_cr_fe_crlibre/models/account_move.py addons/l10n_cr_fe_crlibre/tests/test_account_move_mapping.py
git commit -m "feat(l10n_cr_fe_crlibre): incluir actividad económica del receptor en el XML enviado a Hacienda"
```

---

### Task 10: Verificación manual end-to-end

**Files:** ninguno (solo verificación en el navegador y contra el sandbox real).

- [ ] **Step 1: Actualizar el módulo y reiniciar el servidor**

Run:
```bash
MSYS_NO_PATHCONV=1 docker exec fortuna-odoo-1 odoo -d Fortuna --db_host=db --db_user=odoo --db_password=odoo -u l10n_cr_fe_crlibre --stop-after-init --http-port=8169
docker restart fortuna-odoo-1
```

- [ ] **Step 2: Agregar actividades reales a un cliente de prueba**

En `http://localhost:8069`, crear o abrir un cliente con una cédula real de prueba (ej. `3101042624`, la usada en las pruebas de esta sesión — devuelve al menos una actividad activa contra el sandbox real de Hacienda). Ir a la pestaña "Actividades Económicas ante Hacienda", pulsar "Agregar Actividad Económica", buscar, y agregar 1-2 actividades sin que el wizard se cierre entre una y otra.

- [ ] **Step 3: Confirmar el bloqueo en Orden de venta**

Crear una Orden de venta para ese cliente sin elegir actividad económica y confirmar que "Confirmar" da error pidiendo elegir una. Elegir una actividad y confirmar que sí permite continuar.

- [ ] **Step 4: Confirmar el comportamiento en Factura**

Generar la factura desde esa orden y confirmar que trae la misma actividad ya elegida (sin tener que volver a elegirla). Si esta base tiene credenciales de sandbox de Hacienda configuradas (confirmar antes — si no las hay, omitir el resto de este paso sin bloquear el plan), publicarla y confirmar que no aparece ningún error nuevo relacionado a la actividad económica.

- [ ] **Step 5: Verificar el caso sin actividad en factura**

Crear una factura para un cliente SIN actividades registradas — confirmar que se puede publicar sin pedir ninguna. Crear una factura para un cliente CON actividades pero sin elegir ninguna — confirmar que se publica igual (no bloquea), y que el chatter explica el motivo por el que el envío a Hacienda quedó en error.
