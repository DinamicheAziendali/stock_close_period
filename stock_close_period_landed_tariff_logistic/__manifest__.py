# Copyright 2024 Sergio Corato <https://github.com/sergiocorato>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Stock Close Period Landed Tariff",
    "summary": "Glue module with Stock Close Period and landed custom modules",
    "version": "16.0.1.0.0",
    "category": "Stock",
    "author": "Dinamiche Aziendali srl, Sergio Corato",
    "website": "https://github.com/DinamicheAziendali/stock_close_period",
    "license": "AGPL-3",
    "depends": [
        "stock_close_period",
        "l10n_it_intrastat_tariff",
        "res_country_logistic_charge",
        "res_currency_change_charge",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
