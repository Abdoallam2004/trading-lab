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
