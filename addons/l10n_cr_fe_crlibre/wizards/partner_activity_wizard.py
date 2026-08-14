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
