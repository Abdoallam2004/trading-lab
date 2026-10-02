from lab.universe import exclusion_reason, filter_symbols, is_leveraged


def test_stablecoins_excluded():
    for s in ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "DAIUSDT", "EURUSDT"]:
        assert exclusion_reason(s) == "stablecoin"


def test_leveraged_tokens_excluded_but_jup_kept():
    assert is_leveraged("BTCUP") and is_leveraged("ETHDOWN") and is_leveraged("BNBBULL")
    assert not is_leveraged("JUP")
    assert exclusion_reason("BTCUPUSDT") == "leveraged token"
    assert exclusion_reason("JUPUSDT") is None


def test_meme_and_wrapped_excluded():
    assert exclusion_reason("DOGEUSDT") == "meme coin"
    assert exclusion_reason("PEPEUSDT") == "meme coin"
    assert exclusion_reason("WBTCUSDT") == "wrapped/backed asset"


def test_non_usdt_pairs_rejected():
    assert exclusion_reason("ETHBTC") == "not a USDT pair"


def test_filter_keeps_majors():
    syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "USDCUSDT", "SHIBUSDT", "ETHUPUSDT"]
    assert filter_symbols(syms) == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def test_tokenized_stocks_excluded_but_crypto_ending_in_b_kept():
    for s in ["SKHYBUSDT", "MUBUSDT", "SNXXBUSDT", "AAPLBUSDT", "SPYBUSDT", "NVDABUSDT"]:
        assert exclusion_reason(s) == "tokenized stock/ETF", s
    for s in ["BNBUSDT", "ARBUSDT", "CKBUSDT", "TRBUSDT"]:
        assert exclusion_reason(s) is None, s


def test_new_meme_and_misc_exclusions():
    assert exclusion_reason("GIGGLEUSDT") == "meme coin"
    assert exclusion_reason("币安人生USDT") == "meme coin"
    assert exclusion_reason("BULLUSDT") == "leveraged token"
    assert exclusion_reason("BNSOLUSDT") == "wrapped/backed asset"
    assert exclusion_reason("XECUSDT") is None  # eCash is not a meme coin


def test_excluded_by_reason_groups():
    from lab.universe import excluded_by_reason
    g = excluded_by_reason(["BTCUSDT", "DOGEUSDT", "USDCUSDT", "MUBUSDT"])
    assert g == {"meme coin": ["DOGEUSDT"], "stablecoin": ["USDCUSDT"], "tokenized stock/ETF": ["MUBUSDT"]}
