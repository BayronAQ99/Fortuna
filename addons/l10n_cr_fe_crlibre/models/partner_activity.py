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
