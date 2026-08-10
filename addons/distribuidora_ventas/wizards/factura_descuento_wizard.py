from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FacturaDescuentoWizard(models.TransientModel):
    _name = 'distribuidora.factura.descuento.wizard'
    _description = "Descuento general para facturas de cliente"

    move_id = fields.Many2one(
        'account.move', required=True,
        default=lambda self: self.env.context.get('active_id'),
    )
    porcentaje = fields.Float(string="Porcentaje de descuento", required=True)

    @api.constrains('porcentaje')
    def _check_porcentaje(self):
        for wizard in self:
            if not 0 < wizard.porcentaje <= 100:
                raise ValidationError(_(
                    "El porcentaje de descuento debe ser mayor a 0 y menor o igual a 100."
                ))

    def action_aplicar(self):
        self.ensure_one()
        product_lines = self.move_id.invoice_line_ids.filtered(lambda line: line.display_type == 'product')
        product_lines.write({'discount': self.porcentaje})
