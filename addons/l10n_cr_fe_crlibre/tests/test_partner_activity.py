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
