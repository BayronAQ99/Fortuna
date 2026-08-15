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
