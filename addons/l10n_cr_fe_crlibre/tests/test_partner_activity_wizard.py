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
