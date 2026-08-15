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

    def test_non_6_digit_code_from_hacienda_is_accepted(self):
        # Hacienda's /fe/ae API returns activity codes in this exact
        # non-6-digit format for at least some taxpayers (confirmed live,
        # personas fisicas) - '6201.0' is a real value returned for a real
        # cedula. This must not be rejected: the same value is already used,
        # unvalidated, as this company's own economic_activity_code
        # (l10n_cr.fe.config) and has been accepted by Hacienda's sandbox.
        activity = self.env['l10n_cr.fe.partner.activity'].create({
            'partner_id': self.partner.id, 'code': '6201.0', 'description': 'Actividades de programación informática',
        })
        self.assertEqual(activity.code, '6201.0')

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
