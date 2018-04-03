from .. import indicators as ta
from .. import detection as detect
# from ..sig import Sig
from .base import Strategy, Sig


class vwma_cross(Strategy):

    def __init__(self,window=20,trend=50):
        name = "vwma_cross"
        super().__init__(name)
        self.window = window
        self.trend_window = trend

    def process(self,prices):
        vwma = ta.vwma(self.window,prices)
        ma = ta.ma(self.window,prices)
        trend = ta.ma(self.trend_window,prices)
        
        # look for bullish signals
        if detect.crossover(vwma,ma):
            sig = Sig("VWMA_CROSS",prices[-1]['snapshotTime'],"BUY",1)
            if detect.candleover(trend,prices):
                sig.comment = "confirmed by candleover"
                sig.score = 4
            else:
                sig.score = 2
            
            super().add_signal(sig)

        # look for bearish signals
        if detect.crossunder(vwma,ma):
            sig = Sig("VWMA_CROSS",prices[-1]['snapshotTime'],"SELL",1)
            if detect.candleunder(trend,prices):
                sig.comment = "confirmed by candleunder"
                sig.score = 4
            else:
                sig.score = 2
            super().add_signal(sig)

