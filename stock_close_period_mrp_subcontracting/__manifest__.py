# Copyright 2025 Sergio Corato <https://github.com/sergiocorato>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Stock Close Period - MRP with subcontracting",
    "summary": "Glue module when subcontracting is installed",
    "version": "16.0.1.0.0",
    "category": "Stock",
    "author": "Dinamiche Aziendali srl, Sergio Corato",
    "website": "https://github.com/DinamicheAziendali/stock_close_period",
    "license": "AGPL-3",
    "depends": [
        "stock_close_period_mrp",
        "stock_close_period_direct_cost",
        "mrp_subcontracting",
    ],
    "data": [],
    "installable": True,
    "auto_install": True,
}
