import logging
import os,sys
from numbers import Number
import math
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
    """Creates open signals 
        - checking for MFI cross back from 25 or 75
            - create a signal that lasts 8 periods
        - open long when mfi cross back from <25
            - if close price > ema40
        - open short when mfi cross back from >75
            - if close price < ema40
    """
 
    def __init__(self):
        name = "stoch"
        super().__init__(name)
 
 
        self.last_state = "NONE"
 
    def backfill(self,market,resolution,lookback=18):
        
        print("backtesting slow sigs")
        prices = market.prices['MINUTE_30']
        price_len = len(prices)
        print(price_len - lookback)
        if price_len - lookback < 100:
 
            for i in list(range(lookback,-1,-1)):
                p = price_len - i
                ps = prices[:p]
                print("{} {}".format(market.epic, ps[-1]['snapshotTime']))
                self.slow_signals(market,ps,'MINUTE_30')
 
        print("backtesting fast sigs")
        prices = market.prices['MINUTE_5']
        price_len = len(prices)
        print(price_len - lookback)
        if price_len - lookback < 100:
 
            for i in list(range(lookback,-1,-1)):
                p = price_len - i
                ps = prices[:p]
                print("{} {}".format(market.epic, ps[-1]['snapshotTime']))
                self.fast_signals(market,ps,'MINUTE_5')

    def prediction(self, signal,market,resolution):
        """default stoploss and limit calculator based on atr_14"""
        res = 'MINUTE_5'
        if "SLOW" in signal.name:
            res = "MINUTE_30"
        prices = market.prices[res]
        atr, tr = ta.atr(14,prices)
        low_range = min(tr)
        max_range = max(tr)
 
        
        stop = (atr[-1]*1.44) + (market.spread*2)
        limit = math.ceil(atr[-1]*1.2)
 
        limit = max(limit,4)
        # limit = min(7,limit)
        if signal.position == "BUY":
            # GO LONG
            lows = [x['lowPrice']['mid'] for x in prices[-5:]]
            stop = market.bid - min(lows)
            DIRECTION_TO_TRADE = "BUY"
            DIRECTION_TO_CLOSE = "SELL"
            DIRECTION_TO_COMPARE = 'bid'
            # low = min([x['lowPrice']['bid'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(self.bid - low)
            # stop = abs(self.bid - self.prices[signal.resolution][-2]['lowPrice']['bid'])
 
        else:
            # GO SHORT!
            highs = [x['highPrice']['mid'] for x in prices[-5:]]
            stop = max(highs) - market.offer
            DIRECTION_TO_TRADE = "SELL"
            DIRECTION_TO_CLOSE = "BUY"
            DIRECTION_TO_COMPARE = 'offer'
            # high = max([x['highPrice']['ask'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(high - self.offer)
            # stop = abs(self.prices[signal.resolution][-2]['highPrice']['ask'] - self.offer)
 
        stop =  stop + (market.spread*2)
        # prepare the trade info object to pass back
        prediction_object = {
            "strategy" : self.name,
            "direction_to_trade" : DIRECTION_TO_TRADE,
            "direction_to_close" : DIRECTION_TO_CLOSE,
            "direction_to_compare" : DIRECTION_TO_COMPARE,
            "stoploss" : stop,
            "limit_distance" : limit,
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
            for s in [x for x in self.signals if x.market == market.epic and "FAST" in x.name]:
                if not s.process():
                    print("{} timed out".format(s.name))
                    self.signals.remove(s)
 
            if 'MINUTE_5' not in market.prices:
                return
 
            # maindir = self.maindir(market,"DAY")
            # prices = market.prices['MINUTE_5']
 
            ma7 = ta.ma(7,prices)
            ma50 = ta.ma(40,prices)
            ma100 = ta.ema(80,prices)
 
            ema5 = ta.ma(5,prices)
            stoch_k, stoch_d = ta.stochastic(prices,5,3,3)
            now = prices[-1]
 
            if ma50[-1] > ma100[-1] and ma7[-1] > ma100[-1]:
 
                if detect.crossover(stoch_k,stoch_d) and min(stoch_k[-5:])<20:
                    
                    sig = Sig("STOCH_FAST_STOCH_THRESHOLD",now['snapshotTime'],"BUY",1,comment="stoch_k below threshold {}".format(stoch_k[-1]),life=7)
                    super().add_signal(sig,market)
                
 
            elif ma50[-1] < ma100[-1] and ma7[-1] < ma100[-1]:
   
                if detect.crossunder(stoch_k,stoch_d) and max(stoch_k[-5:])>80:
                    sig = Sig("STOCH_FAST_STOCH_THRESHOLD",now['snapshotTime'],"SELL",1,comment="stoch_k above threshold {}".format(stoch_k[-1]),life=7)
                    super().add_signal(sig,market)
                
            threshold_sigs = [x for x in self.signals if x.name=="STOCH_FAST_STOCH_THRESHOLD" and x.market==market.epic]
 
            # for s in threshold_sigs:
            #     if s.position=="BUY":
            #         if detect.crossover(ema5,ma7):
            #             sig = Sig("STOCH_FAST_MA_CROSS",now['snapshotTime'],"BUY",1,comment="ema5 {} ma7 {}; previous sig {} {}".format(ema5[-1],ma7[-1],s.timestamp,s.comment),life=4)
            #             super().add_signal(sig,market)
            #     else:
            #         if detect.crossunder(ema5,ma7):
            #             sig = Sig("STOCH_FAST_MA_CROSS",now['snapshotTime'],"SELL",1,comment="ema5 {} ma7 {}; previous sig {} {}".format(ema5[-1],ma7[-1],s.timestamp,s.comment),life=4)
            #             super().add_signal(sig,market)
            
            # ma_sigs = [x for x in self.signals if x.name=="STOCH_FAST_MA_CROSS" and x.market==market.epic]
 
            ema5_delta = ema5[-1] - ema5[-2]
            ma7_delta = ma7[-1] - ma7[-2]
            for s in threshold_sigs:
                if s.position=="BUY":
                    if ema5_delta > 0 and ma7_delta > 0:
                        sig = Sig("STOCH_FAST_OPEN",now['snapshotTime'],"BUY",4,comment="stars have aligned 5 min; {} {}".format(s.timestamp,s.comment),life=2)
                        super().add_signal(sig,market)
                        self.signals.remove(s)
                else:
                    if ema5_delta < 0 and ma7_delta < 0:
                        sig = Sig("STOCH_FAST_OPEN",now['snapshotTime'],"SELL",4,comment="stars have aligned 5 min; {} {}".format(s.timestamp,s.comment),life=2)
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
        try:
            for s in [x for x in self.signals if x.market == market.epic and "SLOW" in x.name]:
                if not s.process():
                    print("{} timed out".format(s.name))
                    self.signals.remove(s)
 
            if 'MINUTE_30' not in market.prices:
                return
 
            # maindir = self.maindir(market,"DAY")
            # prices = market.prices['MINUTE_30']
 
            ma7 = ta.ma(7,prices)
            ma50 = ta.ma(40,prices)
            ma100 = ta.ma(80,prices)
 
            ema5 = ta.ema(5,prices)
            stoch_k, stoch_d = ta.stochastic(prices,5,3,3)
            now = prices[-1]
 
            if ma50[-1] > ma100[-1] and ma7[-1] > ma100[-1]:
                
                if detect.crossover(stoch_k,stoch_d) and min(stoch_k[-5:])<25:
                    sig = Sig("STOCH_SLOW_STOCH_THRESHOLD",now['snapshotTime'],"BUY",1,comment="stoch_k below threshold {}".format(stoch_k[-1]),life=7)
                    super().add_signal(sig,market)
                
 
            elif ma50[-1] < ma100[-1] and ma7[-1] < ma100[-1]:
                
                if detect.crossunder(stoch_k,stoch_d) and max(stoch_k[-5:])>75:
                    sig = Sig("STOCH_SLOW_STOCH_THRESHOLD",now['snapshotTime'],"SELL",1,comment="stoch_k above threshold {}".format(stoch_k[-1]),life=7)
                    super().add_signal(sig,market)
                
            threshold_sigs = [x for x in self.signals if x.name=="STOCH_SLOW_STOCH_THRESHOLD" and x.market==market.epic]
 
            # for s in threshold_sigs:
            #     if s.position=="BUY":
            #         if detect.crossover(ema5,ma7):
            #             sig = Sig("STOCH_SLOW_MA_CROSS",now['snapshotTime'],"BUY",1,comment="ema5 {} ma7 {}; previous sig {} {}".format(ema5[-1],ma7[-1],s.timestamp, s.comment),life=4)
            #             super().add_signal(sig,market)
            #     else:
            #         if detect.crossunder(ema5,ma7):
            #             sig = Sig("STOCH_SLOW_MA_CROSS",now['snapshotTime'],"SELL",1,comment="ema5 {} ma7 {}; previous sig {} {}".format(ema5[-1],ma7[-1],s.timestamp, s.comment),life=4)
            #             super().add_signal(sig,market)
 
            # ma_sigs = [x for x in self.signals if x.name=="STOCH_SLOW_MA_CROSS" and x.market==market.epic]
 
            ema5_delta = ema5[-1] - ema5[-2]
            ma7_delta = ma7[-1] - ma7[-2]
            for s in threshold_sigs:
                if s.position=="BUY":
                    if ema5_delta > 0.5:
                        sig = Sig("STOCH_SLOW_OPEN",now['snapshotTime'],"BUY",4,comment="stars have aligned 30 min; {} {}".format(s.timestamp, s.comment),life=2)
                        super().add_signal(sig,market)
                        self.signals.remove(s)
                else:
                    if ema5_delta < -0.5:
                        sig = Sig("STOCH_SLOW_OPEN",now['snapshotTime'],"SELL",4,comment="stars have aligned 30 min; {} {}".format(s.timestamp, s.comment),life=2)
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