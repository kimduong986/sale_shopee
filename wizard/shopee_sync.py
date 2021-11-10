from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime

INTERVAL_GET_ORDER = [
    (3, "3 days before from current date"),
    (2, "2 days before from current date"),
    (1, "1 days before from current date"),
    (0, "Custom Interval Date")
]

class MerchantShopeeWizard(models.TransientModel):
    _name = 'merchant.shopee.wizard'

    merchant_shopee_id = fields.Many2one('merchant.shopee')

    name = fields.Char()
    partner_id = fields.Integer()
    partner_key = fields.Char()
    host = fields.Char()
    order_interval = fields.Selection(INTERVAL_GET_ORDER, default=3)
    order_from_date = fields.Datetime(default=datetime.now())
    order_to_date = fields.Datetime(default=datetime.now())
    redirect_url = fields.Char()

    shop_shopee_ids = fields.One2many('merchant.shopee.shop.wizard', 'merchant_shopee_id')

    @api.onchange('merchant_shopee_id')
    def onchange_merchant_shopee(self):
        if self.merchant_shopee_id:
            self.name = self.merchant_shopee_id.name
            self.partner_id = self.merchant_shopee_id.partner_id
            self.partner_key = self.merchant_shopee_id.partner_key
            self.host = self.merchant_shopee_id.host
            self.redirect_url = self.merchant_shopee_id.redirect_url
            
            self.shop_shopee_ids = [(5, 0, 0)]
            self.shop_shopee_ids = [(0, 0, {
                'shop_shopee_id': shop.id,
                'request_id': shop.request_id,
                'name': shop.name,
                'shop_id': shop.shop_id,
                'country': shop.country,
                'auth_time': shop.auth_time,
                'expire_time': shop.expire_time,
                'status': shop.status,
                'auth_url': shop.auth_url,
                'code': shop.code,
                'access_token': shop.access_token,
                'sync_active': True
            }) for shop in self.merchant_shopee_id.shop_shopee_ids]

    def _order_sync_date_wizard(self):
        result = {}
        format_date = "%Y-%m-%d %H:%M:%S.%f"
        msp = self
        if msp.order_interval:
            days = msp.order_interval
            result['days_interval'] = days
        else:
            result['time_from'] = datetime.strptime(msp.order_from_date.strftime(format_date), format_date) 
            result['time_to'] = datetime.strptime(msp.order_to_date.strftime(format_date), format_date)

        return result

    def order_sync_shopee(self):
        if not self.merchant_shopee_id:
            raise ValidationError(_("Merchant shopee must be set"))

        active_sync = self.shop_shopee_ids.filtered(lambda x: x.sync_active)
        if not active_sync:
            raise ValidationError(_("Can't sync order from shopee, at least there are 1 shop that was in active sync"))

        for shop in active_sync:
            order_date = self._order_sync_date_wizard()
            shop.action_sync_order_wizard(order_date)

class ShopShopeeWizard(models.TransientModel):
    _name = 'merchant.shopee.shop.wizard'
    
    shop_shopee_id = fields.Integer()
    request_id = fields.Char()
    name = fields.Char()
    shop_id = fields.Integer()
    country = fields.Char()
    auth_time = fields.Integer()
    expire_time = fields.Integer()
    status = fields.Char()
    auth_url = fields.Char()
    code = fields.Char()
    access_token = fields.Char()
    merchant_shopee_id = fields.Many2one('merchant.shopee.wizard', ondelete='cascade')
    sync_active = fields.Boolean(string="Sync")

    def action_sync_order_wizard(self, order_date_param):
        shop = self.env['merchant.shopee.shop'].browse(self.shop_shopee_id)
        shop.action_sync_order_shopee(order_date_param)