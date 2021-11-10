from odoo import http
from odoo.tools.config import config
from odoo.http import request, Response

import json
import base64
import werkzeug


class ShopeeCallbackURL(http.Controller):

    @http.route('/api/shopee', auth='public', methods=['GET'])
    def get_order_bulk(self, **kw):
        '''
            GET 
        '''
        shop_id = kw.get('shop_id')
        if shop_id:
            shopee_shop = request.env['merchant.shopee.shop'].sudo().search([('shop_id', '=', int(shop_id))])
            if shopee_shop:
                shopee_shop.write({
                    "code": kw.get('code')
                })
                merchant_shopee_id = shopee_shop.merchant_shopee_id
                redirect_url = self.generate_url(merchant_shopee_id.id)
                shopee_shop.button_shop_details()
                merchant_shopee_id.sudo().message_post(body="Shop ID (%s) has added code (%s), access token (%s). and other shope details" % (shop_id, kw.get('code'), shopee_shop.access_token))
        
                return werkzeug.utils.redirect(redirect_url)

    def generate_url(self, merchant_shopee_id):
        """
        Build the URL to the record's form view.
          - Base URL + Database Name + Record ID + Model Name

        :param self: any Odoo record browse object (with access to env, _cr, and _model)
        :return: string with url
        """
        db = request.env.cr.dbname
        result = "/web?db=%s#id=%s&view_type=form&model=%s" %  (db, merchant_shopee_id, 'merchant.shopee')
        return result

    @http.route('/api/v1/file/shopee/shipping/<int:ref_id>/<view_pdf_name>', type='http', auth="public", website=True, sitemap=False)
    def open_pdf_file(self, ref_id=0, view_pdf_name=None, **kw):
        if ref_id and view_pdf_name:
            res_id = request.env['shopee.shipping.document'].sudo().browse(ref_id)
            if res_id.sp_shipping_document:
                docs = res_id.sp_shipping_document
                base64_pdf = base64.b64decode(docs)
                pdf = base64_pdf
                return self.return_web_pdf_view(pdf)

    def return_web_pdf_view(self, pdf=None):
        pdfhttpheaders = [('Content-Type', 'application/pdf'), ('Content-Length', u'%s' % len(pdf))]
        return request.make_response(pdf, headers=pdfhttpheaders)