# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.addons import decimal_precision as dp
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    # related field to manage closed lines
    active = fields.Boolean(default=True)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # add field to manage closed lines
    active = fields.Boolean(related="move_id.active", store=True, default=True)
    company_id = fields.Many2one(related="move_id.company_id", store=True)

    def recompute_average_cost_period_purchase(self, closing_id):
        _logger.info("Recompute average cost period. Making in 2 phases:")
        _logger.info("[1/2] Recompute cost product purchase")
        _logger.info("[2/2] Write results")

        self._recompute_cost_stock_move_purchase(closing_id)
        self._write_results(closing_id)

        _logger.info("End recompute average cost product")

    def _get_cost_stock_move_purchase_average(
            self, product_id, last_close_date, sm, ph, company_id, closing_line_id, closing_id):
        # recupera i movimenti di magazzino
        move_ids = sm.search([
            ("state", "=", "done"),
            ("product_qty", ">", 0),
            ("product_id", "=", product_id.id),
            ("date", ">", last_close_date),
            ("active", ">=", 0),
            ("company_id", "=", company_id),
        ], order="date")

        first_move_date = False
        qty = 0
        amount = 0
        new_price = 0
        for move_id in move_ids:
            if not first_move_date:
                # init new product
                first_move_date = move_id.date

                # cancella lo storico dei prezzi
                storic_price = ph.search([
                    ("product_id", "=", product_id.id),
                    ("datetime", ">=", first_move_date),
                    ("company_id", "=", company_id),
                ])
                if storic_price:
                    storic_price.unlink()

                # get start data from last close
                start_qty, start_price = self._get_last_closing(closing_id, product_id.id, company_id)

                # se valorizzata, crea la prima riga sullo storico prezzi
                if start_qty:
                    ph.create({
                        "product_id": product_id.id,
                        "datetime": first_move_date,
                        "cost": start_price,
                        "company_id": company_id,
                    })

                    # fissa il punto iniziale
                    amount = start_price * start_qty
                    qty = start_qty
                    new_price = start_price

                else:
                    # se non trova un valore iniziale, imposta il costo al valore
                    # alla data di partenza, altrimenti i movimenti di scarico
                    # rimangono a zero
                    start_price = product_id.get_history_price(company_id, move_id.date)

                    ph.create({
                        "product_id": product_id.id,
                        "datetime": first_move_date,
                        "cost": start_price,
                        "company_id": company_id,
                    })

                    # fissa il punto iniziale
                    amount = 0
                    qty = 0
                    new_price = start_price

            # si tratta di un acquisto
            if move_id.purchase_line_id:

                # è un vero PO da mediare
                # fa prevalere vale il prezzo sul PO nel caso sia stato aggiornato
                try:
                    distribution_obj = self.env["purchase.cost.distribution.line"]
                    distribution_line_id = distribution_obj.sudo().search([
                        ("move_id", "=", move_id.id),
                        ("company_id", "=", company_id),
                    ])
                    standard_price_new = distribution_line_id.standard_price_new
                except:
                    standard_price_new = 0

                if standard_price_new:
                    price = standard_price_new
                elif move_id.purchase_line_id.currency_id == move_id.purchase_line_id.company_id.currency_id:
                    price = move_id.purchase_line_id.price_unit
                else:
                    price = move_id.purchase_line_id.currency_id._convert(
                        move_id.purchase_line_id.price_unit,
                        move_id.purchase_line_id.company_id.currency_id,
                        move_id.purchase_line_id.company_id,
                        move_id.date,
                        False
                    )
                if move_id.price_unit != price:
                    new_price = price
                    move_id.price_unit = new_price
                    move_id.value = move_id.product_uom_qty * new_price
                    move_id.remaining_value = move_id.product_uom_qty * new_price

                # calculate new ovl price if price > 0
                if price > 0:
                    qty += move_id.product_qty
                    amount += (move_id.product_qty * price)

                if qty != 0.0:
                    new_price_ovl = amount / qty
                else:
                    new_price_ovl = 0

                # get history price at move date
                h_price_date_move = product_id.get_history_price(company_id, move_id.date)

                # if new_price_ovl != new_price:
                if new_price_ovl != h_price_date_move:
                    # assegna il nuovo prezzo
                    new_price = new_price_ovl
                    # crea lo storico
                    ph.create({
                        "product_id": move_id.product_id.id,
                        "datetime": move_id.date,
                        "cost": new_price,
                        "company_id": company_id,
                    })

            else:
                # imposta su movimento di magazzino il nuovo costo medio ponderato
                if move_id.price_unit != new_price:
                    # fatto con sql altrimenti l'ORM scatena l'inferno
                    value = move_id.product_uom_qty * new_price
                    remaining_value = move_id.product_uom_qty * new_price

                    # set active = False on stock_move and stock_move_line
                    query = """                        
                        UPDATE 
                            stock_move
                        SET 
                            price_unit = %r,
                            value = %r,
                            remaining_value = %r
                        WHERE
                            id = %r;
                    """ % (new_price, value, remaining_value, move_id.id)
                    self.env.cr.execute(query)

        # memorizzo il risultato alla data di chiusura
        price_unit = product_id.get_history_price(company_id, closing_id.close_date)
        if price_unit == 0:
            closing_line_id.price_unit = product_id.standard_price
            closing_line_id.evaluation_method = "standard"

        closing_line_id.price_unit = price_unit
        closing_line_id.evaluation_method = "purchase"

    def _get_cost_stock_move_standard(self, product_id, closing_id, company_id, closing_line_id):
        # ricalcola std_cost
        # recupera il prezzo standard alla data del movimento
        history_price = self.env["product.price.history"].search([
            ("company_id", "=", company_id),
            ("product_id", "in", product_id.ids),
            ("datetime", ">", closing_id.close_date),
        ])
        if history_price:
            price_unit = product_id.get_history_price(company_id, closing_id.close_date)
        else:
            price_unit = product_id.standard_price

        # se non trova std_cost, prende il prezzo ora disponibile
        if price_unit == 0:
            price_unit = product_id.standard_price

        # memorizzo il risultato
        closing_line_id.price_unit = price_unit
        closing_line_id.evaluation_method = "standard"

    def _recompute_cost_stock_move_purchase(self, closing_id):
        #
        #   Aquisti: Prezzo medio ponderato nel periodo. Esempio:
        #
        #   data        causale             quantità    prezzo unitario     totale      prezzo medio
        #   01/01/19    giacenza iniziale   9390        3,1886              29940,95
        #   12/04/19    carico da aquisto   8000        3,23                25840,00
        #                                   17390                           55780,95    3,2076
        #

        _logger.info("[1/2] Start recompute cost product purchase")
        company_id = self.env.user.company_id.id
        wcp = self.env["stock.close.period"]
        wcpl = self.env["stock.close.period.line"]
        sm = self.env["stock.move"]
        ph = self.env["product.price.history"]

        # search only lines not elaborated
        closing_line_ids = wcpl.search([
            ("close_id", "=", closing_id.id),
            ("evaluation_method", "not in", ["manual"]),
            ("price_unit", "=", 0)
        ])

        # get last_close_date
        if closing_id.last_closed_id:
            last_closed_id = closing_id.last_closed_id
        else:
            last_closed_id = wcp.search([
                ("state", "=", "done"),
                ("company_id", "=", company_id)
            ], order="close_date desc", limit=1)

        if last_closed_id:
            # get from last closed
            last_close_date = last_closed_id.close_date
        else:
            # gel all moves
            last_close_date = "2010-01-01"

        # all closing_line ready to elaborate
        for closing_line_id in closing_line_ids:
            product_id = closing_line_id.product_id

            if closing_id.force_evaluation_method != "no_force" and not closing_line_id.evaluation_method:
                if closing_id.force_evaluation_method == "purchase":
                    self._get_cost_stock_move_purchase_average(
                        product_id, last_close_date, sm, ph, company_id, closing_line_id, closing_id)
                if closing_id.force_evaluation_method == "standard":
                    self._get_cost_stock_move_standard(product_id, closing_id, company_id, closing_line_id)
            else:
                # solo prodotti valutati al medio o standard
                if product_id.categ_id.property_cost_method == "average":
                    self._get_cost_stock_move_purchase_average(
                        product_id, last_close_date, sm, ph, company_id, closing_line_id, closing_id)
                if product_id.categ_id.property_cost_method == "standard":
                    self._get_cost_stock_move_standard(product_id, closing_id, company_id, closing_line_id)

            self.env.cr.commit()
        _logger.info("[1/2] Finish recompute average cost product")

    def _write_results(self, closing_id):
        wcpl = self.env["stock.close.period.line"]
        decimal = dp.get_precision("Product Price")(self._cr)[1]

        # search lines
        closing_line_ids = wcpl.search([("close_id", "=", closing_id.id)])

        _logger.info("[2/2] Start writing results")

        # all closing_line_ids ready to elaborate
        amount = 0
        for closing_line_id in closing_line_ids:
            # calcolo totale per riga
            row_value = closing_line_id.product_qty * closing_line_id.price_unit
            amount += round(row_value, decimal)

        # set amount closing
        closing_id.amount = amount

        _logger.info("[2/2] Finish writing results")

    def _get_last_closing(self, closing_id, product_id, company_id):
        wcp = self.env["stock.close.period"]
        wcpl = self.env["stock.close.period.line"]

        # dafault value
        start_qty = 0
        start_price = 0

        if closing_id.last_closed_id:
            last_closed_id = closing_id.last_closed_id
        else:
            last_closed_id = wcp.search([
                ("state", "=", "done"),
                ("company_id", "=", company_id)
            ], order="close_date desc", limit=1)

        # search product
        closing_line_id = wcpl.search([
            ("close_id", "=", last_closed_id.id),
            ("product_id", "=", product_id)
        ], limit=1)

        if closing_line_id:
            start_qty = closing_line_id.product_qty
            start_price = closing_line_id.price_unit

        return start_qty, start_price
