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

class stoch(Strategy):

    def __init__(self,stoch_len=14,k_smooth=3,d_smooth=3):
        name = "stoch"
        super().__init__(name)
        self.stoch = stoch_len
        self.ksmooth = k_smooth
        self.dsmooth = d_smooth

    def backfill(self,market,resolution):
        super().backfill(market,resolution,15)
                
    def fast_signals(self,market,prices,resolution):
        super().fast_signals(market,prices,resolution)
        if resolution == "MINUTE_5":
            stoch_k, stoch_d = ta.stochastic(prices,self.stoch,self.ksmooth,self.dsmooth)
            prev_avg = (stoch_k[-2] + stoch_d[-2]) / 2
            now_avg = (stoch_k[-1] + stoch_d[-1]) / 2
            
            series = [prev_avg,now_avg]

            now = prices[-1]

            if detect.crossunder(stoch_k,79):
                sig = Sig("STOCH_CLOSE",now['snapshotTime'],"SELL",2,life=2)
                super().add_signal(sig,market)
            
            if detect.crossover(stoch_k,21):
                sig = Sig("STOCH_CLOSE",now['snapshotTime'],"BUY",2,life=2)
                super().add_signal(sig,market)



    def slow_signals(self,market,prices, resolution):
        super().slow_signals(market,prices,resolution)
        # what's the dailies saying?
        
        day_wma25 = ta.wma(25,market.prices['DAY'])

        # want to look at the daily trends before even considering opening a position
        daydir = "NONE"
        wma_delta = day_wma25[-1] - day_wma25[-2]
        if wma_delta > 0:
            daydir = "BUY"
        
        if wma_delta < 0:
            daydir = "SELL"

        now = prices[-1]
        
        if resolution=="MINUTE_5":
            wma25 = ta.wma(25,prices)
            # check if the price action is matching the day wma
            roc = ta.roc(36,prices)
            if daydir=="BUY" and roc[-1] < 0:
                daydir = "NONE"
            if daydir=="SELL" and roc[-1] > 0:
                daydir = "NONE"

            stoch_k, stoch_d = ta.stochastic(prices,self.stoch,self.ksmooth,self.dsmooth)
            stoch_k_delta = stoch_k[-1] - stoch_k[-3]
            if daydir =="BUY":
                if 70 > stoch_k[-1] > 55 and stoch_k[-3]<50:
                    sig = Sig("STOCH_OPEN",now['snapshotTime'],"BUY",1,comment = "",life=2)
                    super().add_signal(sig,market)
            elif daydir=="SELL":
                if stoch_k[-1]<45 and stoch_k[-3]>50:
                    sig = Sig("STOCH_OPEN",now['snapshotTime'],"SELL",1,comment = "",life=2)
                    super().add_signal(sig,market)

            open_sigs = [x for x in self.signals if x.name=="STOCH_OPEN" and x.market==market.epic]
            wma_delt = wma25[-1] - wma25[-2]
            for s in open_sigs:
                if s.position=="BUY":
                    if wma_delt > 0:
                        sig = Sig("STOCH_CONFIRM",now['snapshotTime'],"BUY",4,comment = "orig: {}".format(sig.timestamp),life=1)
                        super().add_signal(sig,market)
                        self.signals.remove(s)
                else:
                    if wma_delt < 0:
                        sig = Sig("STOCH_CONFIRM",now['snapshotTime'],"SELL",4,comment = "orig: {}".format(sig.timestamp),life=1)
                        super().add_signal(sig,market)
                        self.signals.remove(s)



    
   