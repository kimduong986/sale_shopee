from odoo import models, fields, api, _
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError

import tzlocal
import pytz
import hmac
import time
import requests
import hashlib
import json

INTERVAL_GET_ORDER = [
    (3, "3 days before from current date"),
    (2, "2 days before from current date"),
    (1, "1 days before from current date"),
    (0, "Custom Interval Date")
]

SHOPEE_ORDER_STATUS = [
    ('UNPAID', 'UNPAID'),
    ('READY_TO_SHIP', 'READY TO SHIP'),
    ('RETRY_SHIP', 'RETRY SHIP'),
    ('IN_CANCEL', 'IN CANCEL'),
    ('CANCELLED', 'CANCELLED'),
    ('PROCESSED', 'PROCESSED'),
    ('SHIPPED', 'SHIPPED'),
    ('TO_RETURN', 'TO RETURN'),
    ('TO_CONFIRM_RECEIVE', 'TO CONFIRM RECEIVE'),
    ('COMPLETED', 'COMPLETED')
]

BASE_HOST = "https://partner.shopeemobile.com"

class MerchantShopee(models.Model):
    _name = 'merchant.shopee'
    _inherit = ['mail.thread']

    name = fields.Char()
    partner_id = fields.Integer()
    partner_key = fields.Char()
    host = fields.Char(default=BASE_HOST)
    order_interval = fields.Selection(INTERVAL_GET_ORDER, default=3)
    order_from_date = fields.Datetime(default=datetime.now())
    order_to_date = fields.Datetime(default=datetime.now())
    redirect_url = fields.Char(default=lambda self: self._callback_url())
    active = fields.Boolean(default=True)

    shop_shopee_ids = fields.One2many('merchant.shopee.shop', 'merchant_shopee_id')

    def _callback_url(self):
        base_url = self.env['ir.config_parameter'].get_param('web.base.url')
        return "%s/api/shopee" % (base_url)

    def generate_url_shopee(self, path, redirect_url=None):
        timest = int(time.time())
        host = self.host
        partner_id = self.partner_id
        partner_key = self.partner_key
        base_string = "%s%s%s" % (partner_id, path, timest)
        sign = hmac.new(bytes(partner_key , 'utf-8'), bytes(base_string , 'utf-8'), hashlib.sha256).hexdigest()

        params = "?partner_id=%s&timestamp=%s&sign=%s" % (
            partner_id,
            timest,
            sign
        )
        generate_url = "%s%s%s" % (host, path, params)
        if redirect_url:
            generate_url = "%s&redirect=%s" % (generate_url, redirect_url)

        return generate_url

    def _order_sync_date(self):
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

    def button_sync_all_order(self):
        order_date = self._order_sync_date()

        for shop in self.shop_shopee_ids:
            shop.action_sync_order_shopee(order_date)

    def _cron_shopee_sync_order(self):
        merchant_shopee = self.search([])
        for ms in merchant_shopee:
            try:
                ms.button_sync_all_order()
            except Exception as ex:
                ms.message_post(body="failed to sync shopee order from cron/scheduler: %s" % (ex))
    
    def generate_datetime_jakarta(self, date_int):
        # return datetime.fromtimestamp(date_int) - timedelta(hours=7)
        return datetime.fromtimestamp(date_int)

    def get_shop_list(self):
        for rec in self:
            shop_ids = []
            generate_url = self.generate_url_shopee("/api/v2/public/get_shops_by_partner")
            url = "%s&page_size=%s&page_no=%s" % (generate_url, 1, 1)
            try:
                r = requests.get(url)
                r.raise_for_status()
            except Exception as ex:
                response = json.loads(r.text)
                message = "Failed sync shopee shops: %s, %s" % (ex, response)
                rec.message_post(body=message)
            else:
                status_code = r.status_code
                response = json.loads(r.text)
                request_id = response.get('request_id')
                if request_id:
                    rec.shop_shopee_ids = [(5, 0, 0)]
                    auth_shops = response.get('authed_shop_list')
                    for shop in auth_shops:
                        shop_id = shop.get('shop_id')
                        redirect_url = self.redirect_url
                        shop_auth_url = self.generate_url_shopee("/api/v2/shop/auth_partner", redirect_url)
                        shop_ids.append((0, 0, {
                            "shop_id": shop.get('shop_id'),
                            "auth_time": shop.get('auth_time'),
                            "expire_time": shop.get('expire_time'),
                            "date_auth": self.generate_datetime_jakarta(shop.get('auth_time')),
                            "date_expired": self.generate_datetime_jakarta(shop.get('expire_time')),
                            "country": shop.get('region'),
                            "auth_url": shop_auth_url,
                            "affi_shop_ids": [(0, 0, {
                                "affi_shop_id": afs["affi_shop_id"],
                                "region": afs["region"]
                            }) for afs in shop['sip_affi_shop_list']]
                        }))

                    rec.shop_shopee_ids = shop_ids
                    rec.message_post(body="Add Shops: %s" % (shop_ids))
    
    def get_access_token(self):
        for rec in self:
            for shop in rec.shop_shopee_ids:
                if not shop.access_token and shop.code:
                    shop.button_shop_details()

    def refresh_token_shop(self):
        for rec in self:
            for shop in rec.shop_shopee_ids:
                if shop.access_token and shop.refresh_token:
                    shop.button_refresh_token()

    @api.model
    def _cron_accounts_generate_refresh_access_token(self):
        shopee_accounts = self.search([])
        for account in shopee_accounts:
            account.refresh_token_shop()

class MerchantShopeeShop(models.Model):
    _name = 'merchant.shopee.shop'

    merchant_shopee_id = fields.Many2one('merchant.shopee', ondelete='cascade')
    request_id = fields.Char()
    name = fields.Char()
    shop_id = fields.Integer()
    country = fields.Char()
    auth_time = fields.Integer()
    expire_time = fields.Integer()
    date_auth = fields.Datetime()
    date_expired = fields.Datetime()
    token_expired = fields.Datetime()
    status = fields.Char()
    auth_url = fields.Char()
    code = fields.Char()
    access_token = fields.Char()
    refresh_token = fields.Char()
    affi_shop_ids = fields.One2many('merchant.shopee.shop.affi', 'shopee_shop_id')

    def get_token_shop_level(self, code, partner_id, partner_key, shop_id):
        url = self.merchant_shopee_id.generate_url_shopee("/api/v2/auth/token/get")
        
        body = {"code": code, "shop_id": shop_id, "partner_id": partner_id}
        headers = {'Content-Type': 'application/json'}
        try:
            r = requests.post(url, data=json.dumps(body), headers=headers)
            r.raise_for_status()
        except Exception as ex:
            response = json.loads(r.text)
            message = "Failed sync shopee shop access token: %s, %s" % (ex, response)
            self.merchant_shopee_id.message_post(body=message)
        else:
            response = json.loads(r.text)
            return {
                'access_token': response.get('access_token'), 
                'expire_in': response.get('expire_in'),
                'refresh_token': response.get('refresh_token')
            }

    def get_refresh_token(self, partner_id, shop_id, refresh_token):
        url = self.merchant_shopee_id.generate_url_shopee("/api/v2/auth/access_token/get")
        
        body = {"shop_id": shop_id, "refresh_token": refresh_token, "partner_id": partner_id}
        headers = {'Content-Type': 'application/json'}
        try:
            r = requests.post(url, data=json.dumps(body), headers=headers)
            r.raise_for_status()
        except Exception as ex:
            response = json.loads(r.text)
            message = "Failed sync shopee shop refresh token: %s, %s" % (ex, response)
            self.merchant_shopee_id.message_post(body=message)
        else:
            response = json.loads(r.text)
            return response

    def get_auth_shop_code(self):
        if not self.auth_url:
            raise ValidationError(_("Auth URL is empty"))

        return {                   
            'name'     : 'Get Auth Shopee Shop',
            'res_model': 'ir.actions.act_url',
            'type'     : 'ir.actions.act_url',
            'target'   : 'new',
            'url'      : self.auth_url
        }

    def generate_url_shop_info(self, path):
        if not self.access_token:
            raise ValidationError(_("Access token is empty you need to generate access token first"))

        timest = int(time.time())
        host = self.merchant_shopee_id.host
        partner_id = self.merchant_shopee_id.partner_id
        partner_key = self.merchant_shopee_id.partner_key
        access_token = self.access_token
        shop_id = self.shop_id
        base_string = "%s%s%s%s%s" % (partner_id, path, timest, access_token, shop_id)
        sign = hmac.new(bytes(partner_key , 'utf-8'), bytes(base_string , 'utf-8'), hashlib.sha256).hexdigest()

        params = "?partner_id=%s&timestamp=%s&sign=%s&access_token=%s&shop_id=%s" % (
            partner_id,
            timest,
            sign,
            access_token,
            shop_id
        )
        generate_url = "%s%s%s" % (host, path, params)

        return generate_url

    def button_refresh_token(self):
        if not self.refresh_token:
            raise ValidationError(_("There are no refresh token ready.."))

        if self.refresh_token:
            params = {
                "partner_id": self.merchant_shopee_id.partner_id,
                "refresh_token": self.refresh_token,
                "shop_id": self.shop_id
            }
            generate_refresh_token = self.get_refresh_token(**params)
            if generate_refresh_token:
                self.write({
                    'access_token': generate_refresh_token['access_token'],
                    'token_expired': datetime.now() + timedelta(0, generate_refresh_token['expire_in']),
                    'refresh_token': generate_refresh_token['refresh_token']
                })
                self.merchant_shopee_id.message_post(body="Refresh token is success: %s" % (generate_refresh_token))

    def button_shop_details(self):
        if not self.code:
            raise ValidationError(_("You need to get code of shop from the Auth URL first"))

        if not self.access_token:
            params = {
                "code": self.code,
                "partner_id": self.merchant_shopee_id.partner_id,
                "partner_key": self.merchant_shopee_id.partner_key,
                "shop_id": self.shop_id
            }
            generate_access_token = self.get_token_shop_level(**params)
            if generate_access_token:
                self.write({
                    'access_token': generate_access_token['access_token'],
                    'token_expired': datetime.now() + timedelta(0, generate_access_token['expire_in']),
                    'refresh_token': generate_access_token['refresh_token']
                })

        try:
            generate_url = self.generate_url_shop_info("/api/v2/shop/get_shop_info")
            url = generate_url
            r = requests.get(url)
            r.raise_for_status()
        except Exception as ex:
            response = json.loads(r.text)
            message = "Failed sync shopee shop details info: %s, %s" % (ex, response)
            self.merchant_shopee_id.message_post(body=message)
        else:
            response = json.loads(r.text)
            if response.get('shop_name'):
                self.write({
                    'name': response.get('shop_name'),
                    'status': response.get('status')
                })

    def _sync_order(self, time_from=False, time_to=False, days_interval=False):
        generate_url = self.generate_url_shop_info("/api/v2/order/get_order_list")
        date_end_sync = time_to
        if not date_end_sync:
            date_end_sync = datetime.today()

        date_start_sync = time_from
        if not date_start_sync:
            date_start_sync = date_end_sync - timedelta(days=days_interval)

        # Convert Timezone To UTC For Filtering. Because Timezone in Database is UTC
        server_timezone = tzlocal.get_localzone().zone
        dss_utc = pytz.timezone(server_timezone).localize(date_start_sync).astimezone(pytz.UTC)
        des_utc = pytz.timezone(server_timezone).localize(date_end_sync).astimezone(pytz.UTC)
        dss_utc_string = dss_utc.strftime("%Y-%m-%d %H:%M:%S")
        des_utc_string = des_utc.strftime("%Y-%m-%d %H:%M:%S")
        # +7 Hours For Parameter UNIX Timestamp in API Tokopedia. TO CONVERT THIS CAN NOT USE TIMEZONE and .timestamp(), because .timestamp() always in UTC+0
        dss_tokopedia = dss_utc + timedelta(hours=7)
        des_tokopedia = des_utc + timedelta(hours=7)
        timestamp_start_tokopedia = int(dss_tokopedia.timestamp())
        timestamp_end_tokopedia = int(des_tokopedia.timestamp())
        data_order = []
        added_params = "&time_range_field=%s&time_from=%s&time_to=%s&page_size=%s&order_status=%s&response_optional_fields=%s" % (
            "create_time",
            timestamp_start_tokopedia,
            timestamp_end_tokopedia,
            100,
            "READY_TO_SHIP",
            "order_status"
        )
        try:
            url = "%s%s" % (generate_url, added_params)
            r = requests.get(url)
            r.raise_for_status()
        except Exception as ex:
            response = json.loads(r.text)
            message = "Failed sync shopee order list: %s, %s" % (ex, response)
            self.merchant_shopee_id.message_post(body=message)
            return False
        else:
            response = json.loads(r.text)
            if response.get('response'):
                response['url'] = url
                return response
            
            return False

    def _sync_order_details(self, order_sn_list):
        generate_url = self.generate_url_shop_info("/api/v2/order/get_order_detail")
        detail_fields = [
            'buyer_user_id',
            'buyer_username',
            'recipient_address',
            'note',
            'item_list',
            'pay_time',
            'buyer_cancel_reason',
            'cancel_by',
            'cancel_reason',
            'shipping_carrier',
            'payment_method',
            'total_amount',
            'invoice_data',
            'package_list'
            # 'checkout_shipping_carrier',
            # 'note_update_time',
            # 'estimated_shipping_fee',
            # 'goods_to_declare',
            # 'actual_shipping_fee',
            # 'pickup_done_time',
            # 'reverse_shipping_fee',
            # 'fulfillment_flag',
            # 'buyer_cpf_id',
            # 'actual_shipping_fee_confirmed',
            # 'dropshipper',
            # 'credit_card_number',
            # 'dropshipper_phone',
            # 'split_up',
        ]
        
        added_params = "&order_sn_list=%s&response_optional_fields=%s" % (','.join(order_sn_list), ','.join(detail_fields))
        try:
            url = "%s%s" % (generate_url, added_params)
            r = requests.get(url)
            r.raise_for_status()
        except Exception as ex:
            response = json.loads(r.text)
            message = "Failed sync shopee order details %s: %s, %s" % (order_sn_list, ex, response)
            self.merchant_shopee_id.message_post(body=message)
            return False
        else:
            response = json.loads(r.text)
            if response.get('response'):
                response['url'] = url
                return response
            
            return False

    def action_sync_order_shopee(self, param):
        get_order_list = self._sync_order(**param)
        created_new_customer = []
        data_order = []
        cancel_request = []
        if get_order_list:
            shopee_order_list = get_order_list.get('response').get('order_list')
            if shopee_order_list:
                for shopee_order in shopee_order_list:
                    odoo_so = self.env['sale.order'].search([('sp_order_sn', '=', shopee_order['order_sn'])])
                    if not odoo_so:
                        shopee_order_details = self._sync_order_details([shopee_order['order_sn']])
                        response = shopee_order_details.get('response')
                        if response:
                            order = response.get('order_list')[0]
                            if order:
                                customer_ref = "SP%s" % (order['buyer_user_id'])
                                buyer_full_name = order['recipient_address']['name']
                                customer_order_id = self.env['res.partner'].search([('ref', '=', customer_ref)])
                                if not customer_order_id:
                                    customer_order_id = self.env['res.partner'].create({
                                        'name': buyer_full_name,
                                        'ref': customer_ref,
                                        'customer': True,
                                        'mobile': order['recipient_address']['phone'],
                                        'street': order['recipient_address']['full_address']
                                    })
                                    created_new_customer.append({
                                        'name': customer_order_id.name,
                                        'id': customer_order_id.id,
                                        'ref': customer_order_id.ref
                                    })

                                order_lines = order['item_list']
                                sale_order_line = []
                                for line in order_lines:
                                    product_tmpl_id = self.env['product.template'].search(['|', ('default_code', '=', line['item_sku']), ('name', '=', line['item_name'])])
                                    if not product_tmpl_id:
                                        raise ValidationError(_("Product is not found by SKU '%s' or Name '%s'" % (line['item_sku'], line['item_name'])))

                                    product_product = self.env['product.product'].search([('product_tmpl_id', '=', product_tmpl_id[0].id)])
                                    sale_order_line.append((0, 0 ,{
                                        'product_id': product_product.id,
                                        'product_uom_qty': float(line['model_quantity_purchased']),
                                        'price_unit': float(line['model_original_price'])
                                    }))
                                
                                shopee_date_order = datetime.fromtimestamp(
                                   order['create_time']
                                ) - timedelta(hours=7)
                                
                                package_list = order['package_list']
                                shipping_document_ids = [(0, 0, {
                                    'sp_package_number': package.get('package_number'),
                                    'sp_shipping_carrier': package.get('shipping_carrier'),
                                    'sp_logistic_status': package.get('logistics_status'),
                                    'sp_item_list_ids': [(0, 0, {
                                        'model_id': package_item.get('model_id'),
                                        'item_id': package_item.get('item_id')
                                    }) for package_item in package.get('item_list')]
                                }) for package in package_list]

                                vals = {
                                    'sp_id': self.merchant_shopee_id.id,
                                    'sp_shop_id': self.shop_id,
                                    'sp_order_sn': order['order_sn'],
                                    'sp_order_status': order['order_status'],
                                    'sp_buyer_user_id': order['buyer_user_id'],
                                    'sp_buyer_username': order['buyer_username'],
                                    'sp_buyer_name': order['recipient_address']['name'],
                                    'sp_buyer_phone': order['recipient_address']['phone'],
                                    'sp_buyer_fulladdress': order['recipient_address']['full_address'],
                                    'sp_invoice_number': str(order['invoice_data']),
                                    'sp_payment_method': order['payment_method'],
                                    'sp_shipping_document_ids': shipping_document_ids,
                                    'sp_note': order['note'],
                                    'date_order': shopee_date_order,
                                    'partner_id': customer_order_id.id,
                                    'order_line': sale_order_line
                                }

                                if order['cancel_by']:
                                    vals['sp_cancel_by'] = order['cancel_by']
                                    vals['sp_cancel_reason'] = order['cancel_reason']
                                    vals['sp_buyer_cancel_reason'] = order['buyer_cancel_reason']

                                create_sale_order = self.env['sale.order'].create(vals)

                                date_order_result = {
                                    'sale_id': create_sale_order.id,
                                    'sale_number': create_sale_order.name,
                                    'shopee_order_id': create_sale_order.sp_order_sn,
                                    'order_lines': [{
                                        'sku': ol['item_sku'],
                                        'name': ol['item_name'],
                                        'quantity': ol['model_quantity_purchased'],
                                        'price': ol['model_original_price']
                                    } for ol in order_lines],
                                }

                                if create_sale_order.sp_cancel_by:
                                    cancel_request.append({
                                        'sale_number': create_sale_order.name,
                                        'shopee_order': create_sale_order.sp_order_sn,
                                        'cancel_request_detail': {
                                            'reason': create_sale_order.sp_buyer_cancel_reason if create_sale_order.sp_buyer_cancel_reason else create_sale_order.sp_cancel_reason,
                                            'by': create_sale_order.sp_cancel_by
                                        }
                                    })

                                data_order.append(date_order_result)
                
            created_order_message = {
                'order_created': {
                    'total': len(data_order),
                    'order_details': data_order
                },
                'created_customer': created_new_customer,
                'order_cancel_request': cancel_request
            }

            self.merchant_shopee_id.message_post(body=created_order_message)

    def button_sync_order(self):
        order_sync_param = self.merchant_shopee_id._order_sync_date()
        self.action_sync_order_shopee(order_sync_param)

class MerchantShopeeShopSip(models.Model):
    _name = 'merchant.shopee.shop.affi'

    shopee_shop_id = fields.Many2one('merchant.shopee.shop')
    affi_shop_id = fields.Integer()
    region = fields.Char()

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            if record.affi_shop_id:
                result.append((record.id, "[%s] %s" % (record.region, record.affi_shop_id)))

        return result

