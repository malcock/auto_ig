from .. import indicators as ta
from .. import detection as detect
from .base import Strategy, Sig


class wma_cross(Strategy):

    def __init__(self,fast=10, slow=25, trend=50, rsi_len = 14):
        name = "wma_cross"
        super().__init__(name)
        self.fast = fast
        self.slow = slow
        self.trend_window = trend
        self.rsi = rsi_len

    def backfill(self,prices):
        super().backfill(prices,15)
                

    def process(self,prices):
        print("processing... {}".format(prices[-1]['snapshotTime']))
        if len(prices)<50:
            return
        slow = ta.wma(self.slow,prices)
        fast = ta.wma(self.fast,prices)
        trend = ta.wma(self.trend_window,prices)
        rsi = ta.rsi(self.rsi,prices)
        now = prices[-1]

        # look for bullish signals
        if detect.crossover(fast,slow):
            sig = Sig("WMA_CROSS",now['snapshotTime'],"BUY",2,life=12)
            super().add_signal(sig)

            # if we match all open conditions, create an additional CONFIRM signal
            if (detect.isbelow(trend[-1], now['openPrice']['bid'],now['closePrice']['bid'])):
                if rsi[-1] > rsi[-2]:
                    sig = Sig("WMA_CROSS_CONFIRM",now['snapshotTime'],"BUY",4,comment = "confirmed by trend below candle and good rsi",life=1)
                    super().add_signal(sig)
                
                

        # look for bearish signals
        if detect.crossunder(fast,slow):
            sig = Sig("WMA_CROSS",now['snapshotTime'],"SELL",2,life=12)
            super().add_signal(sig)
            # if we match all open conditions, create an additional CONFIRM signal
            if (detect.isabove(trend[-1], now['openPrice']['bid'],now['closePrice']['bid'])):
                if rsi[-1] < rsi[-2]:
                    sig = Sig("WMA_CROSS_CONFIRM",now['snapshotTime'],"SELL",4,comment = "confirmed by trend below candle", life=1)
                    super().add_signal(sig)
            

        # look for confirmation signals
        cross_sigs = [x for x in self.signals if x.name=="WMA_CROSS"]
        for s in cross_sigs:
            if s.position=="BUY":
                if detect.candleover(trend,prices):
                    sigC = Sig("WMA_CONFIRM",now['snapshotTime'],"BUY",4)
                    sigC.comment = "confirmed by candle over"
                    super().add_signal(sigC)
            else:
                if detect.candleunder(trend,prices):
                    sigC = Sig("WMA_CONFIRM",now['snapshotTime'],"SELL",4)
                    sigC.comment = "confirmed by candle under"
                    super().add_signal(sigC)


        super().process(prices)

    def entry(self, signal, prices):
        """wma entry strategy
            candle and rsi delta must be in direction of trade and rsi must not be over/undersold
        """
        now = prices[-1]
        rsi_name = 'rsi_{}'.format(self.rsi)
        rsi = now[rsi_name]
        rsi_delta = rsi - prices[-2][rsi_name]
        if signal['position']=="BUY":
            if rsi < 70 and rsi_delta>0 and now['dir'] > 0:
                return True
        else:
            if rsi > 30 and rsi_delta<0 and now['dir'] < 0:
                return True

        return False


            