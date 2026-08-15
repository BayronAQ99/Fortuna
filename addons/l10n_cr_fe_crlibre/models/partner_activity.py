from odoo import fields, models


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
