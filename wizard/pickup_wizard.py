from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime

class ShopeePickupWizard(models.TransientModel):
    _name = 'shopee.pickup.wizard'

    sale_id = fields.Many2one('sale.order')
    order_sn = fields.Char()
    info_needed_type = fields.Selection([
        ('dropoff', 'Drop-off'),
        ('pickup', 'Pick-up')
    ])
    info_needed_param_ids = fields.Many2many('info.needed.wizard')
    pickup_time_ids = fields.One2many('shopee.pickup.time.wizard', 'shopee_pickup_id')

    def do_action_pickup(self):
        selected_pickup_time = self.pickup_time_ids.filtered(lambda x: x.selected)
        if len(selected_pickup_time) > 1:
            raise ValidationError(_("You can only select 1 pick up time"))
        
        body_pickup = {
            "info_needed_type": self.info_needed_type,
            "content": {
                "address_id": selected_pickup_time.address_id,
                "pickup_time_id": selected_pickup_time.pickup_time_id
            } 
        }
        shopee_order = self.sale_id.do_pickup(self.order_sn, body_pickup)

class InfoNeededParams(models.TransientModel):
    _name = 'info.needed.wizard'

    name = fields.Char()

class ShopeePickupTimeWizard(models.TransientModel):
    _name = 'shopee.pickup.time.wizard'

    address_id = fields.Integer()
    address = fields.Text()
    time_text = fields.Char()
    date = fields.Date()
    pickup_time_id = fields.Char()
    shopee_pickup_id = fields.Many2one('shopee.pickup.wizard')
    selected = fields.Boolean()