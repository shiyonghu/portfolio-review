from portfolio.accounts.tax import derive_tax_treatment


def test_brokerage_is_taxable():
    assert derive_tax_treatment("brokerage") == "taxable"


def test_checking_is_taxable():
    assert derive_tax_treatment("checking") == "taxable"


def test_ira_is_tax_advantaged():
    assert derive_tax_treatment("ira") == "tax-advantaged"


def test_roth_ira_is_tax_advantaged():
    assert derive_tax_treatment("roth ira") == "tax-advantaged"


def test_401k_is_tax_advantaged():
    assert derive_tax_treatment("401k") == "tax-advantaged"


def test_529_is_tax_advantaged():
    assert derive_tax_treatment("529") == "tax-advantaged"


def test_hsa_is_tax_advantaged():
    assert derive_tax_treatment("hsa") == "tax-advantaged"


def test_unknown_defaults_taxable():
    assert derive_tax_treatment("other") == "taxable"
    assert derive_tax_treatment(None) == "taxable"
