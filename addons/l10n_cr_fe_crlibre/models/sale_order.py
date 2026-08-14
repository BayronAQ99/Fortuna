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
