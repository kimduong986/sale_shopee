odoo.define('sale_shopee.ShopeeButtonMenu', function(require) {
    "use strict";

var Widget = require('web.Widget');
var core = require('web.core');
var SystrayMenu = require('web.SystrayMenu');
var ShopeeButtonMenu = Widget.extend({    
    template:'ShopeeButtonMenu',
    events: {
        "click": "on_click"
    },
    on_click: function (event) {
        var self = this;
        var _t = core._t;
        self.do_action({
            type: 'ir.actions.act_window',
            name: _t('Shopee Sync Order'),
            res_model: 'merchant.shopee.wizard',
            view_type: 'form',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new'
        });
    }
});
SystrayMenu.Items.push(ShopeeButtonMenu);

return ShopeeButtonMenu;
});