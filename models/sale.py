from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from . import merchant_shopee as ms

from datetime import datetime, timedelta
import json
import requests
import base64
import logging
_logger = logging.getLogger(__name__)

GET_SHIPPING_DOC_PARAM = "/api/v2/logistics/get_shipping_document_parameter"
CREATE_SHIPPING_DOC = "/api/v2/logistics/create_shipping_document"
GET_SHIPPING_DOC_RESULT = "/api/v2/logistics/get_shipping_document_result"
DOWNLOAD_SHIPPING_DOC = "/api/v2/logistics/download_shipping_document"
GET_TRACKING_NUMBER = "/api/v2/logistics/get_tracking_number"

class SaleOrderShopeeInherit(models.Model):
    _inherit = 'sale.order'

    sp_id = fields.Many2one('merchant.shopee')
    sp_order_sn = fields.Char()
    sp_order_status = fields.Selection(ms.SHOPEE_ORDER_STATUS)
    sp_shop_id = fields.Integer()

    sp_buyer_user_id = fields.Integer()
    sp_buyer_username = fields.Char()
    sp_buyer_name = fields.Char()
    sp_buyer_phone = fields.Char()
    sp_buyer_fulladdress = fields.Text()

    sp_invoice_number = fields.Char()

    sp_pay_time = fields.Datetime()
    sp_payment_method = fields.Char()
    
    sp_cancel_by = fields.Datetime('Cancel By')
    sp_cancel_reason = fields.Char('Reason')
    sp_buyer_cancel_reason = fields.Char('Buyer Cancel Reason')

    sp_note = fields.Text()

    shopee_order = fields.Char(compute="_compute_shopee_order")

    #logistic
    sp_shipping_document_ids = fields.One2many('shopee.shipping.document', 'sale_id')

    def _compute_shopee_order(self):
        for rec in self:
            rec.shopee_order = ""
            if rec.sp_order_status and rec.sp_order_sn:
                rec.shopee_order = "[ID: %s] %s" % (rec.sp_order_sn, rec.sp_order_status)

    def get_shipping_parameter(self, order_sn):
        shopee_shop_id = self.sp_id.shop_shopee_ids.filtered(lambda x: x.shop_id == self.sp_shop_id)
        if shopee_shop_id:
            generate_url = shopee_shop_id.generate_url_shop_info("/api/v2/logistics/get_shipping_parameter")
            try:
                added_params = "&order_sn=%s" % (order_sn)
                url = "%s%s" % (generate_url, added_params)
                r = requests.get(url)
                r.raise_for_status()
            except Exception as ex:
                response = json.loads(r.text)
                message = "Failed sync shopee request parameters %s: %s, %s" % (order_sn, ex, response)
                self.message_post(body=message)
                return False
            else:
                response = json.loads(r.text)
                if response:
                    if not response.get('error'):
                        context = {
                            'sale_id': self.id,
                            'order_sn': order_sn
                        }
                        result = response.get('response')
                        pickup_time_ids = []
                        if result['info_needed']['pickup']:
                            context['info_needed_type'] = "pickup"
                            context['info_needed_param_ids'] = [(0, 0, {'name': ifp}) for ifp in result['info_needed']['pickup']]
                            for a_l in result['pickup']['address_list']:
                                for timeslot in a_l['time_slot_list']:
                                    date_timeslot = shopee_date_order = datetime.fromtimestamp(
                                        timeslot['date']
                                    ) - timedelta(hours=7)

                                    pickup_time_ids.append((0, 0, {
                                        'address_id': a_l['address_id'],
                                        'date': date_timeslot,
                                        'time_text': timeslot['time_text'],
                                        'address': a_l['address'],
                                        'pickup_time_id': timeslot['pickup_time_id']
                                    }))

                            context['pickup_time_ids'] = pickup_time_ids
                            
                        elif result['info_needed']['dropoff']:
                            raise ValidationError(_("Currently we dont have feature for drop-off yet: %s" % (response)))

                        new = self.env['shopee.pickup.wizard'].create({
                            'sale_id': context['sale_id'],
                            'order_sn': context['order_sn'],
                            'info_needed_type': context['info_needed_type'],
                            'info_needed_param_ids': context['info_needed_param_ids'],
                            'pickup_time_ids': context['pickup_time_ids'],                             
                        })

                        return {
                            'type': 'ir.actions.act_window',
                            'name': 'Shopee Pickup: Select pickup time',
                            'res_model': 'shopee.pickup.wizard',
                            'view_type': 'form',
                            'res_id'    : new.id,
                            'view_mode': 'form',
                            'target': 'new'
                        }                     

    def action_shopee_request_pickup(self):
        for rec in self:
            if rec.sp_id and rec.sp_order_sn and rec.sp_order_status == 'READY_TO_SHIP':
                return self.get_shipping_parameter(rec.sp_order_sn)

    def generate_url_order_ship(self, order_sn, body_pickup):
        shopee_shop_id = self.sp_id.shop_shopee_ids.filtered(lambda x: x.shop_id == self.sp_shop_id)
        if shopee_shop_id:
            generate_url = shopee_shop_id.generate_url_shop_info("/api/v2/logistics/ship_order")
            try:
                body = {
                    "order_sn": order_sn
                }
                body[body_pickup['info_needed_type']] = body_pickup['content']

                headers = {'Content-Type': 'application/json'}
                r = requests.post(generate_url, data=json.dumps(body), headers=headers)
                r.raise_for_status()
            except Exception as ex:
                response = json.loads(r.text)
                message = "Failed sync shopee request pickup %s: %s, %s" % (order_sn, ex, response)
                self.message_post(body=message)
                return False
            else:
                response = json.loads(r.text)
                if response:
                    response['url'] = generate_url
                    return response

                return False
    
    def do_pickup(self, order_sn, body_pickup):
        shopee_request_pickup = self.generate_url_order_ship(order_sn, body_pickup)
        if shopee_request_pickup:
            self.message_post(body="Request pick-up shopee order: %s" % (shopee_request_pickup))
            if not shopee_request_pickup.get('error'):
                self.message_post(body="Shopee request pickup success: %s" % (shopee_request_pickup))
                self.write({
                    'sp_order_status': 'PROCESSED'
                })
            else:
                raise ValidationError(_("Failed do request pickup on shopee order: %s" % (shopee_request_pickup)))

class ShopeeShippingDocument(models.Model):
    _name = 'shopee.shipping.document'

    sale_id = fields.Many2one('sale.order', ondelete='cascade')
    sp_package_number = fields.Char(string="Package Number")
    sp_shipping_carrier = fields.Char(string="Shipping Carrier")
    sp_logistic_status = fields.Char(string="Logistic Status")
    sp_item_list_ids = fields.One2many('shopee.shipping.item', 'shipping_id')

    sp_tracking_number = fields.Char()
    sp_shipping_document_type = fields.Char(string="Shipping Document Type")
    sp_selectable_shipping_document_type_ids = fields.One2many(
        'selectable.shipping.document', 
        'shipping_id'
    )
    sp_fail_error = fields.Char(string="Fail Error")
    sp_fail_message = fields.Char(string="Fail Message")
    sp_created_document = fields.Boolean(string="Is Created?")
    sp_shipping_document = fields.Binary(string="Shipping File")

    def get_shipping_doc_param(self):
        shopee_shop_id = self.sale_id.sp_id.shop_shopee_ids.filtered(lambda x: x.shop_id == self.sale_id.sp_shop_id)
        if shopee_shop_id:
            generate_url = shopee_shop_id.generate_url_shop_info(GET_SHIPPING_DOC_PARAM)
            try:
                body = {
                    "order_list": [{
                        "order_sn": self.sale_id.sp_order_sn,
                        "package_number": self.sp_package_number
                    }]
                }
                headers = {'Content-Type': 'application/json'}
                r = requests.post(generate_url, data=json.dumps(body), headers=headers)
                r.raise_for_status()
            except Exception as ex:
                response = json.loads(r.text)
                message = "Failed sync shopee get shipping document parameters %s/%s: %s, %s" % (
                    self.sale_id.sp_order_sn, 
                    self.sp_package_number,
                    ex, 
                    response
                )
                self.sale_id.message_post(body=message)
                return False
            else:
                response = json.loads(r.text)
                if response:
                    response['url'] = generate_url
                    return response

                return False
    
    def get_tracking_number(self):
        shopee_shop_id = self.sale_id.sp_id.shop_shopee_ids.filtered(lambda x: x.shop_id == self.sale_id.sp_shop_id)
        if shopee_shop_id:
            generate_url = shopee_shop_id.generate_url_shop_info(GET_TRACKING_NUMBER)
            added_params = "&order_sn=%s&package_number=%s" % (self.sale_id.sp_order_sn, self.sp_package_number)
            try:
                url = "%s%s" % (generate_url, added_params)
                r = requests.get(url)
                r.raise_for_status()
            except Exception as ex:
                response = json.loads(r.text)
                message = "Failed sync shopee get tracking number %s/%s: %s, %s" % (
                    self.sale_id.sp_order_sn, 
                    self.sp_package_number,
                    ex, 
                    response
                )
                self.sale_id.message_post(body=message)
                return False
            else:
                response = json.loads(r.text)
                if response:
                    response['url'] = generate_url
                    return response

                return False

    def create_shipping_document(self):
        shopee_shop_id = self.sale_id.sp_id.shop_shopee_ids.filtered(lambda x: x.shop_id == self.sale_id.sp_shop_id)
        if shopee_shop_id:
            generate_url = shopee_shop_id.generate_url_shop_info(CREATE_SHIPPING_DOC)
            try:
                body = {
                    "order_list": [{
                        "order_sn": self.sale_id.sp_order_sn,
                        "package_number": self.sp_package_number,
                        "tracking_number": self.sp_tracking_number,
                        "shipping_document_type": self.sp_shipping_document_type
                    }]
                }
                headers = {'Content-Type': 'application/json'}
                r = requests.post(generate_url, data=json.dumps(body), headers=headers)
                r.raise_for_status()
            except Exception as ex:
                response = json.loads(r.text)
                message = "Failed sync shopee create shipping document %s/%s: %s, %s" % (
                    self.sale_id.sp_order_sn, 
                    self.sp_package_number,
                    ex, 
                    response
                )
                self.sale_id.message_post(body=message)
                return False
            else:
                response = json.loads(r.text)
                if response:
                    response['url'] = generate_url
                    return response

                return False

    def download_doc_file(self):
        shopee_shop_id = self.sale_id.sp_id.shop_shopee_ids.filtered(lambda x: x.shop_id == self.sale_id.sp_shop_id)
        if shopee_shop_id:
            generate_url = shopee_shop_id.generate_url_shop_info(DOWNLOAD_SHIPPING_DOC)
            try:
                body = {
                    "shipping_document_type": self.sp_shipping_document_type,
                    "order_list": [{
                        "order_sn": self.sale_id.sp_order_sn,
                        "package_number": self.sp_package_number
                    }]
                }
                headers = {'Content-Type': 'application/json'}
                r = requests.post(generate_url, data=json.dumps(body), headers=headers)
                r.raise_for_status()
            except Exception as ex:
                response = json.loads(r.text)
                message = "Failed sync shopee download shipping document %s/%s: %s, %s" % (
                    self.sale_id.sp_order_sn, 
                    self.sp_package_number,
                    ex, 
                    response
                )
                self.sale_id.message_post(body=message)
                return False
            else:
                return r.content

    def download_shipping_doc(self):
        order_sn = self.sale_id.sp_order_sn
        package_number = self.sp_package_number
        get_params = self.get_shipping_doc_param()
        if get_params:
            response = get_params.get('response')
            if not response:
                raise ValidationError(_("Failed get param shipping doc: %s" % (get_params)))

            result_list = response.get('result_list')
            if result_list:
                param = result_list[0]
                self.sp_selectable_shipping_document_type_ids = [(5, 0, 0)]
                if param.get('order_sn') == order_sn and param.get('package_number') == package_number:
                    if not param.get('fail_error'):
                        self.write({
                            'sp_shipping_document_type': param.get('suggest_shipping_document_type'),
                            'sp_selectable_shipping_document_type_ids': [(0, 0, {
                                'name': selectable
                            }) for selectable in param.get('selectable_shipping_document_type')]
                        })
                    else:
                        message_err = {
                            'sp_fail_error': param.get('fail_error'),
                            'sp_fail_message': param.get('fail_message')
                        }
                        self.write(message_err)
                        self.sale_id.message_post(body=message_err)

        get_tracking_number = self.get_tracking_number()
        if get_tracking_number:
            if get_tracking_number.get('error'):
                self.sale_id.message_post(body=get_tracking_number)
            else:
                response = get_tracking_number.get('response')
                if not response:
                    raise ValidationError(_("Failed get tracking number: %s" % (get_tracking_number)))

                if response:
                    if response.get('tracking_number'):
                        self.write({
                            'sp_tracking_number': response.get('tracking_number')
                        })

        create_shipping_doc = self.create_shipping_document()
        if create_shipping_doc:
            response = create_shipping_doc.get('response')
            if not response:
                raise ValidationError(_("Failed create shipping doc: %s" % (create_shipping_doc)))

            result_list = response.get('result_list')
            if result_list:
                param = result_list[0]
                if param.get('order_sn') == order_sn and param.get('package_number') == package_number:
                    if not param.get('fail_error'):
                        self.write({
                            'sp_created_document': True,
                        })
                    else:
                        message_err = {
                            'sp_fail_error': param.get('fail_error'),
                            'sp_fail_message': param.get('fail_message')
                        }
                        self.write(message_err)
                        self.sale_id.message_post(body=response)

        download_file = self.download_doc_file()
        if download_file:
            file_encode = base64.b64encode(download_file)
            self.write({
                'sp_shipping_document': file_encode
            })

    def show_shopee_shipping_label(self):
        if not self.sp_shipping_document:
            raise ValidationError(_("There are no shipping document! please generate the document first with button 'Get Shipping Label'"))

        url = "/api/v1/file/shopee/shipping/%s/%s_shipping_label" % (self.id, self.sale_id.sp_order_sn)
        return {                   
            'name'     : 'Shipping Label Shopee',
            'res_model': 'ir.actions.act_url',
            'type'     : 'ir.actions.act_url',
            'target'   : 'new',
            'url'      : url
        }
        
class ShopeeSelectableShippingDoc(models.Model):
    _name = 'selectable.shipping.document'

    name = fields.Char()
    shipping_id = fields.Many2one('shopee.shipping.document', ondelete='cascade')

class ShopeeShippingItem(models.Model):
    _name = 'shopee.shipping.item'

    model_id = fields.Char()
    item_id = fields.Char()
    shipping_id = fields.Many2one('shopee.shipping.document', ondelete='cascade')

    @api.multi
    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, "Item ID: %s" % (record.item_id)))

        return result

class ShopeeSaleOrderLineInherit(models.Model):
    _inherit = 'sale.order.line'

    shopee_order_line_id = fields.Integer(string="Shopee Order Detail ID")
