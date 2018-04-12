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
    
    def prediction(self, signal,market,resolution):
        """default stoploss and limit calculator based on atr_5"""
        prices = market.prices['MINUTE_5']
        atr, tr = ta.atr(5,prices)
        low_range = min(tr)
        max_range = max(tr)
        
        stop = (atr[-1] * 2) + (market.spread*1.5)
        if signal.position == "BUY":
            # GO LONG
            DIRECTION_TO_TRADE = "BUY"
            DIRECTION_TO_CLOSE = "SELL"
            DIRECTION_TO_COMPARE = 'bid'
            # low = min([x['lowPrice']['bid'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(self.bid - low)
            # stop = abs(self.bid - self.prices[signal.resolution][-2]['lowPrice']['bid'])

        else:
            # GO SHORT!
            DIRECTION_TO_TRADE = "SELL"
            DIRECTION_TO_CLOSE = "BUY"
            DIRECTION_TO_COMPARE = 'offer'
            # high = max([x['highPrice']['ask'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(high - self.offer)
            # stop = abs(self.prices[signal.resolution][-2]['highPrice']['ask'] - self.offer)


        # prepare the trade info object to pass back
        prediction_object = {
            "strategy" : self.name,
            "direction_to_trade" : DIRECTION_TO_TRADE,
            "direction_to_close" : DIRECTION_TO_CLOSE,
            "direction_to_compare" : DIRECTION_TO_COMPARE,
            "atr_low" : low_range,
            "atr_max" : max_range,
            "stoploss" : stop,
            "limit_distance" : -1,
            "signal" : {
                "timestamp":signal.timestamp,
                "name" : signal.name,
                "position" : signal.position,
                "comment" : signal.comment
            }
            
        }

        return prediction_object


    def fast_signals(self,market,prices,resolution):
        try:
            for s in [x for x in self.signals if x.market == market.epic]:
                if not s.process():
                    print("{} timed out".format(s.name))
                    self.signals.remove(s)
            if 'MINUTE_5' not in market.prices:
                return

            prices = market.prices['MINUTE_5']
            if resolution == "MINUTE_30":
                stoch_k, stoch_d = ta.stochastic(prices,self.stoch,self.ksmooth,self.dsmooth)
                prev_avg = (stoch_k[-2] + stoch_d[-2]) / 2
                now_avg = (stoch_k[-1] + stoch_d[-1]) / 2
                
                series = [prev_avg,now_avg]

                now = prices[-1]

                if detect.crossunder(stoch_k,79):
                    sig = Sig("STOCH_CLOSE",now['snapshotTime'],"SELL",2,life=1)
                    super().add_signal(sig,market)
                
                if detect.crossover(stoch_k,21):
                    sig = Sig("STOCH_CLOSE",now['snapshotTime'],"BUY",2,life=1)
                    super().add_signal(sig,market)

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
            
            if resolution=="MINUTE_30":
                wma25 = ta.wma(25,prices)
                # check if the price action is matching the day wma
                roc = ta.roc(36,market.prices['MINUTE_30'])
                if daydir=="BUY" and roc[-1] < 0:
                    daydir = "NONE"
                if daydir=="SELL" and roc[-1] > 0:
                    daydir = "NONE"

                stoch_k, stoch_d = ta.stochastic(prices,self.stoch,self.ksmooth,self.dsmooth)
                stoch_k_delta = stoch_k[-1] - stoch_k[-3]
                if daydir =="BUY":
                    if 70 > stoch_k[-1] > 55 and stoch_k[-3]<50:
                        sig = Sig("STOCH_OPEN",now['snapshotTime'],"BUY",1,comment = "mid cross",life=2)
                        super().add_signal(sig,market)
                    
                    if detect.crossover(stoch_k,stoch_d) and 80 > stoch_d[-3] > 50:
                        sig = Sig("STOCH_OPEN",now['snapshotTime'],"BUY",1,comment = "mini reversal",life=2)
                        super().add_signal(sig,market)
                        
                elif daydir=="SELL":
                    if stoch_k[-1]<45 and stoch_k[-3]>50:
                        sig = Sig("STOCH_OPEN",now['snapshotTime'],"SELL",1,comment = "mid cross",life=2)
                        super().add_signal(sig,market)
                    
                    if detect.crossunder(stoch_k,stoch_d) and 50 > stoch_d[-3] > 20:
                        sig = Sig("STOCH_OPEN",now['snapshotTime'],"SELL",1,comment = "mini reversal",life=2)
                        super().add_signal(sig,market)
                    

                open_sigs = [x for x in self.signals if x.name=="STOCH_OPEN" and x.market==market.epic]
                wma_delt = wma25[-1] - wma25[-2]
                for s in open_sigs:
                    if s.position=="BUY":
                        if wma_delt > 0:
                            sig = Sig("STOCH_CONFIRM",now['snapshotTime'],"BUY",4,comment = "orig: {} | {}".format(s.timestamp,s.comment),life=1)
                            super().add_signal(sig,market)
                            self.signals.remove(s)
                    else:
                        if wma_delt < 0:
                            sig = Sig("STOCH_CONFIRM",now['snapshotTime'],"SELL",4,comment = "orig: {} | {}".format(s.timestamp,s.comment),life=1)
                            super().add_signal(sig,market)
                            self.signals.remove(s)
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info("{} live fail".format(market.epic))
            logger.info(exc_type)
            logger.info(fname)
            logger.info(exc_tb.tb_lineno)
            logger.info(exc_obj)
            pass


    def slow_signals(self,market,prices, resolution):
        self.fast_signals(market,prices,resolution)
        



    
   