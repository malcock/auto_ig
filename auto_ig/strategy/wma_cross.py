import logging
import os,sys
from .. import indicators as ta
from .. import detection as detect
from .base import Strategy, Sig

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('faig_debug.log')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)

class wma_cross(Strategy):

    def __init__(self,fast=10, slow=25, trend=50, rsi_len = 14):
        name = "wma_cross"
        super().__init__(name)
        self.fast = fast
        self.slow = slow
        self.trend_window = trend
        self.rsi = rsi_len

    def backfill(self,market,resolution):
        super().backfill(market,resolution,15)
                
    def fast_signals(self,market,prices,resolution):
        super().fast_signals(market,prices,resolution)
        # stoch, d = ta.stochastic(prices,14,3,3)
        # now = prices[-1]
        # # check for bull closes
        # nowstoch = stoch[-1]
        # maxstoch = max(stoch[-4:])
        # if nowstoch < 75 and maxstoch > 80 and abs(nowstoch-maxstoch)>4:
        #     sig = Sig("STOCH_CLOSE",now['snapshotTime'],"SELL",2,life=1)
        #     super().add_signal(sig,market)
        
        # # check for bear closes
        # minstoch = min(stoch[-4:])
        # if nowstoch > 25 and minstoch < 20 and abs(nowstoch-minstoch)>4:
        #     sig = Sig("STOCH_CLOSE",now['snapshotTime'],"BUY",2,life=1)
        #     super().add_signal(sig,market)


    def slow_signals(self,market,prices, resolution):
        super().slow_signals(market,prices,resolution)
        # what's the dailies saying?
        day_k, day_d = ta.stochastic(market.prices["DAY"],14,3,3)
        day_wma25 = ta.wma(25,market.prices['DAY'])

        # want to look at the daily trends before even considering opening a position
        daydir = "NONE"
        stoch_delta = day_k[-1] - day_d[-1]
        wma_delta = day_wma25[-1] - day_wma25[-2]
        if (stoch_delta > 0 or day_k[-1] > 85) and wma_delta > 0:
            daydir = "BUY"
        
        if (stoch_delta < 0 or day_k[-1] < 15) and wma_delta < 0:
            daydir = "SELL"

        
        if resolution=="MINUTE_30":
            print("processing... {}".format(prices[-1]['snapshotTime']))
            if len(prices)<50:
                return
            slow = ta.wma(self.slow,prices)
            fast = ta.wma(self.fast,prices)
            trend = ta.wma(self.trend_window,prices)
            
            now = prices[-1]

            # look for bullish wma signals
            if detect.crossover(fast,slow):
                sig = Sig("WMA_CROSS",now['snapshotTime'],"BUY",2,life=7)
                super().add_signal(sig,market)

                # if we match all open conditions, create an additional CONFIRM signal
                if (detect.isabove(trend[-1], trend[-2])):
                    if daydir=="BUY":
                        sig = Sig("WMA_CROSS_CONFIRM",now['snapshotTime'],"BUY",4,comment = "confirmed by all trends on cross",life=1)
                        super().add_signal(sig,market)

            # look for bearish wma signals
            if detect.crossunder(fast,slow):
                sig = Sig("WMA_CROSS",now['snapshotTime'],"SELL",2,life=7)
                super().add_signal(sig,market)
                # if we match all open conditions, create an additional CONFIRM signal
                if (detect.isbelow(trend[-1], trend[-2])):
                    if daydir=="SELL":
                        sig = Sig("WMA_CROSS_CONFIRM",now['snapshotTime'],"SELL",4,comment = "confirmed by all trends on cross", life=1)
                        super().add_signal(sig,market)
                

            # look for confirmation signals
            cross_sigs = [x for x in self.signals if x.name=="WMA_CROSS" and x.market==market.epic]
            for s in cross_sigs:
                if s.position=="BUY":
                    if detect.isabove(trend[-1], trend[-2]) and daydir=="BUY":
                        sigC = Sig("WMA_CONFIRM",now['snapshotTime'],"BUY",4)
                        sigC.comment = "confirmed by trend"
                        super().add_signal(sigC,market)
                else:
                    if detect.isbelow(trend[-1], trend[-2]) and daydir=="SELL":
                        sigC = Sig("WMA_CONFIRM",now['snapshotTime'],"SELL",4)
                        sigC.comment = "confirmed by trend"
                        super().add_signal(sigC,market)


        

    def entry(self, signal, prices):
        """wma entry strategy
            candle and rsi delta must be in direction of trade and rsi must not be over/undersold
        """
        
        direction = prices[-1]['closePrice']['bid'] - prices[-2]['openPrice']['bid']
        rsi_name = 'rsi_{}'.format(self.rsi)
        try:
            rsi = [x[rsi_name] for x in prices]
        except Exception:
            rsi = ta.rsi(self.rsi,prices)
        
        rsi_delta = rsi[-1] - rsi[-2]
        if signal['position']=="BUY":
            if rsi[-1] < 70 and rsi_delta>0 and direction > 0:
                return True
        else:
            if rsi [-1]> 30 and rsi_delta<0 and direction < 0:
                return True



        return False


            