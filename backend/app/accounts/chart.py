"""The starting chart of accounts.

Tally's primary groups, because the accountant already thinks in them and the
books are eventually reconciled against Tally. Ledgers with a system key are
the ones the posting engine writes to; the accountant may rename them and set
their opening balances, but not move or close them, because every bill and
receipt depends on them being where the engine expects.

(code, name, nature, parent code)
"""

GROUPS = [
    ("ASSETS", "Assets", "asset", None),
    ("CUR_ASSETS", "Current assets", "asset", "ASSETS"),
    ("CASH", "Cash-in-hand", "asset", "CUR_ASSETS"),
    ("BANK", "Bank accounts", "asset", "CUR_ASSETS"),
    ("DEBTORS", "Sundry debtors", "asset", "CUR_ASSETS"),
    ("SUSPENSE", "Suspense account", "asset", "ASSETS"),
    ("LIAB", "Liabilities", "liability", None),
    ("CUR_LIAB", "Current liabilities", "liability", "LIAB"),
    ("ADVANCES", "Advances from patients", "liability", "CUR_LIAB"),
    ("CONS_PAYABLE", "Consultant fees payable", "liability", "CUR_LIAB"),
    ("DUTIES", "Duties and taxes", "liability", "CUR_LIAB"),
    ("CAPITAL", "Capital account", "equity", None),
    ("INCOME", "Income", "income", None),
    ("DIRECT_INC", "Direct incomes", "income", "INCOME"),
    ("INDIRECT_INC", "Indirect incomes", "income", "INCOME"),
    ("EXPENSES", "Expenses", "expense", None),
    ("DIRECT_EXP", "Direct expenses", "expense", "EXPENSES"),
    ("INDIRECT_EXP", "Indirect expenses", "expense", "EXPENSES"),
]

# (system key, code, name, group code)
LEDGERS = [
    ("cash", "L-CASH", "Cash in hand", "CASH"),
    ("bank_main", "L-BANK", "Main bank account", "BANK"),
    ("bank_card", "L-CARD", "Card settlements", "BANK"),
    ("bank_upi", "L-UPI", "UPI collections", "BANK"),
    ("bank_neft", "L-NEFT", "Net banking receipts", "BANK"),
    ("cheques", "L-CHQ", "Cheques in hand", "CUR_ASSETS"),
    ("patient_debtors", "L-PATDR", "Patients receivable", "DEBTORS"),
    ("insurance_receivable", "L-INSDR", "Insurance and TPA receivable", "DEBTORS"),
    ("tds_receivable", "L-TDSR", "TDS deducted by payers", "CUR_ASSETS"),
    ("unreceipted_advances", "L-UNREC", "Advances not receipted (before receipts)", "SUSPENSE"),
    ("suspense", "L-SUSP", "Suspense", "SUSPENSE"),
    ("patient_advances", "L-ADV", "Patient advances", "ADVANCES"),
    ("gst_output", "L-GST", "GST output", "DUTIES"),
    ("tds_payable", "L-TDS", "TDS payable", "DUTIES"),
    ("income_consultation", "L-I-CONS", "OPD consultation fees", "DIRECT_INC"),
    ("income_registration", "L-I-REG", "Registration fees", "DIRECT_INC"),
    ("income_procedure", "L-I-PROC", "Procedure income", "DIRECT_INC"),
    ("income_investigation", "L-I-INV", "Investigation income", "DIRECT_INC"),
    ("income_lab", "L-I-LAB", "Laboratory income", "DIRECT_INC"),
    ("income_ipd", "L-I-IPD", "Inpatient services income", "DIRECT_INC"),
    ("income_other", "L-I-OTH", "Other hospital income", "DIRECT_INC"),
    ("consultant_fees", "L-E-CONS", "Consultant fees", "DIRECT_EXP"),
    ("discount_allowed", "L-E-DISC", "Discounts allowed", "INDIRECT_EXP"),
    ("waivers", "L-E-WAIV", "Waivers and write-offs", "INDIRECT_EXP"),
    ("claim_deductions", "L-E-CLMD", "Insurance claim deductions", "INDIRECT_EXP"),
]

NATURES = ("asset", "liability", "equity", "income", "expense")
