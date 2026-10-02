"""Universe selection: which USDT spot pairs are eligible.

Excluded:
  * stablecoins / fiat tokens (trading them against USDT is pointless)
  * leveraged tokens (BTCUP, ETHDOWN, ...): built on leverage, not allowed here
  * meme coins (pure speculation / gharar)
  * wrapped / duplicate assets (WBTC, WBETH, ...) and asset-backed tokens (PAXG)
  * tokenized stocks/ETFs (AAPLB, NVDAB, SKHYB, SPYB, ...): base ends in "B", except
    the real crypto assets in CRYPTO_ENDING_IN_B
  * SHARIA_EXCLUDE: a small, editable list of tokens whose core business is
    interest-based lending or gambling. This is a starting point, not a fatwa.
"""
from __future__ import annotations

from .config import QUOTE

STABLECOINS = {
    "USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PAX", "USDD", "PYUSD",
    "UST", "USTC", "USDE", "USD1", "RLUSD", "BFUSD", "XUSD", "USDS", "SUSD", "GUSD",
    "LUSD", "FRAX", "EUR", "EURI", "AEUR", "GBP", "AUD", "BRL", "TRY", "RUB", "UAH",
    "ZAR", "NGN", "BIDR", "IDRT", "BVND", "VAI", "U", "USDSB", "USDSOLD", "BKRW", "KGST",
}

# Roots that Binance issued UP/DOWN/BULL/BEAR leveraged tokens for.
_LEVERAGED_ROOTS = {
    "BTC", "ETH", "BNB", "XRP", "ADA", "LINK", "DOT", "TRX", "EOS", "LTC", "XTZ",
    "FIL", "SXP", "YFI", "SUSHI", "UNI", "AAVE", "1INCH", "XLM", "BCH",
}
_LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
_LEVERAGED_EXACT = {"BULL", "BEAR", "ETHBULL", "ETHBEAR", "BNBBULL", "BNBBEAR", "EOSBULL", "EOSBEAR",
                    "XRPBULL", "XRPBEAR"}

MEME_COINS = {
    "DOGE", "SHIB", "1000SHIB", "PEPE", "1000PEPE", "FLOKI", "1000FLOKI", "BONK",
    "1000BONK", "WIF", "BOME", "MEME", "PEOPLE", "1000SATS", "TURBO", "NEIRO",
    "1000CAT", "PNUT", "ACT", "DOGS", "MEW", "BRETT", "POPCAT", "TRUMP", "MOODENG",
    "GOAT", "CHILLGUY", "BABYDOGE", "1MBABYDOGE", "1000CHEEMS", "CHEEMS", "SPX",
    "PENGU", "MUBARAK", "BROCCOLI714", "TUT", "BANANAS31", "KOMA", "HIPPO", "PONKE",
    "SLERF", "MYRO", "LADYS", "AIDOGE", "ELON", "WOJAK", "SUNDOG", "FARTCOIN",
    "NOT", "HMSTR", "CATI", "LUNC", "GIGGLE", "TST", "PUMP", "币安人生",
}

WRAPPED_OR_BACKED = {"WBTC", "WBETH", "BETH", "WETH", "PAXG", "XAUT", "BTCB", "STETH", "BNSOL"}

# Real crypto assets whose ticker happens to end in "B" (everything else ending in B on
# Binance spot is a tokenized stock/ETF listed from mid-2026: AAPLB, NVDAB, SKHYB, MUB ...).
CRYPTO_ENDING_IN_B = {"BNB", "ARB", "AMB", "BB", "CKB", "DGB", "MOB", "PHB", "TRB", "VIB", "YB", "SHIB"}

# Editable. Core business = interest-based lending/borrowing or gambling.
SHARIA_EXCLUDE = {"AAVE", "COMP", "XVS", "MORPHO", "JST", "WIN", "FUN", "CREAM", "ALPACA"}


def base_asset(symbol: str, quote: str = QUOTE) -> str:
    if not symbol.endswith(quote):
        raise ValueError(f"{symbol} is not a {quote} pair")
    return symbol[: -len(quote)]


def is_tokenized_stock(base: str) -> bool:
    return len(base) >= 3 and base.endswith("B") and base not in CRYPTO_ENDING_IN_B


def is_leveraged(base: str) -> bool:
    if base in _LEVERAGED_EXACT:
        return True
    for suffix in _LEVERAGED_SUFFIXES:
        if base.endswith(suffix) and base[: -len(suffix)] in _LEVERAGED_ROOTS:
            return True
    return False


def exclusion_reason(symbol: str, quote: str = QUOTE) -> str | None:
    """Return why a symbol is excluded, or None if it is eligible."""
    if not symbol.endswith(quote) or symbol == quote:
        return "not a USDT pair"
    base = base_asset(symbol, quote)
    if base in STABLECOINS:
        return "stablecoin"
    if is_leveraged(base):
        return "leveraged token"
    if base in MEME_COINS:
        return "meme coin"
    if base in WRAPPED_OR_BACKED:
        return "wrapped/backed asset"
    if is_tokenized_stock(base):
        return "tokenized stock/ETF"
    if base in SHARIA_EXCLUDE:
        return "sharia screen (lending/gambling)"
    return None


def excluded_by_reason(symbols: list[str], quote: str = QUOTE) -> dict[str, list[str]]:
    """{reason: [symbols]} for every excluded symbol."""
    out: dict[str, list[str]] = {}
    for s in symbols:
        r = exclusion_reason(s, quote)
        if r:
            out.setdefault(r, []).append(s)
    return {k: sorted(v) for k, v in sorted(out.items())}


def filter_symbols(symbols: list[str], quote: str = QUOTE) -> list[str]:
    return [s for s in symbols if exclusion_reason(s, quote) is None]
