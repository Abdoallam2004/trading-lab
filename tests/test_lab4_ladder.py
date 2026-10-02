import numpy as np
import pandas as pd

from lab4.ladder import ladder


class FakeHourly:
    def __init__(self, closes):
        self.index = pd.date_range("2022-01-01", periods=len(closes), freq="1h", tz="UTC")
        c = np.asarray(closes, float)
        self.o = np.r_[c[0], c[:-1]]
        self.c = c
        self.h = np.maximum(self.o, c) * 1.001
        self.l = np.minimum(self.o, c) * 0.999


def test_ladder_buys_down_and_sells_each_lot_at_its_own_target():
    path = [100] * 5 + [94] * 5 + [88] * 5 + [99] * 5 + [110] * 30   # -6%, -12%, then +12% recovery
    hb = FakeHourly(path)
    m = ladder(hb, hb.index[0], hb.index[-1], g=0.05, n=5, tp="g")
    assert m["x_round_trips"] >= 3          # every lot bought on the way down was sold on the way up
    assert m["multiple"] > 1.0               # never sold at a loss, so a full recovery ends in profit


def test_ladder_never_sells_below_cost():
    path = [100] * 5 + [90] * 50             # falls and never recovers
    hb = FakeHourly(path)
    m = ladder(hb, hb.index[0], hb.index[-1], g=0.05, n=5, tp="g")
    assert m["x_round_trips"] == 0
    assert m["multiple"] < 1.0 and m["max_dd"] > 0
