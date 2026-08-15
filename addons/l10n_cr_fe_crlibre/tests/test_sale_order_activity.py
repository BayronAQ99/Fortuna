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

    def test_confirm_with_activity_from_other_partner_raises(self):
        """El onchange no corre en write()/imports — action_confirm debe
        rechazar igual una actividad que quedó asignada a un partner distinto
        del actual, para no filtrar el código de actividad equivocado en el
        XML cuando la orden se facture."""
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '561001', 'description': 'Restaurantes',
        })
        other_partner = self.env['res.partner'].create({'name': 'Otro Cliente'})
        order = self._create_order(partner=other_partner)
        # write() bypasses the onchange, simulating a stale activity surviving
        # a partner change.
        order.write({'l10n_cr_fe_activity_id': activity.id})
        with self.assertRaises(UserError):
            order.action_confirm()
