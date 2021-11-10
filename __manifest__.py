# -*- coding: utf-8 -*-
{
	'name': "Sale Shopee",
	'summary': """
		Sale Shopee""",
	'description': """
		Sale Shopee x Odoo Integration
	""",
	'author': "Fahmi Roihanul Firdaus",
	'website': "https://www.frayhands.com",
	'version': '0.1',
	'category': 'Uncategorized',
	'version': '0.1',
	'depends': ['mail', 'base', 'sale', 'purchase', 'stock'],
	'images': ['static/description/icon.png'],
	'data': [
		'security/group.xml',
		'security/ir.model.access.csv',
		'views/merchant_shopee_views.xml',
		'views/sale_shopee_templates.xml',
		'views/sale_views.xml',
		'data/refresh_token.xml',
		'wizard/shopee_sync_views.xml',
		'wizard/pickup_views_wizard.xml'
	],
	'qweb': ['static/src/xml/systray.xml'],
}
