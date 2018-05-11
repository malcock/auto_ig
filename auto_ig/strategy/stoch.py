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

    def backfill(self,market,resolution,lookback=10):

        prices = market.prices['MINUTE_5']
        price_len = len(prices)
        if price_len - lookback > 40:

            for i in list(range(lookback,-1,-1)):
                p = price_len - i
                ps = prices[:p]
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
        limit = math.ceil(atr[-1]*0.75)

        limit = max(limit,4)
        limit = min(7,limit)
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
            prices = market.prices['MINUTE_5']

            ma = ta.ma(60,prices)
            cp = [x['closePrice']['mid'] for x in prices]
            stoch_k, stoch_d = ta.stochastic(prices,5,3,3)


            now = prices[-1]
            if detect.crossover(stoch_k,stoch_d) and min(stoch_k[-5:])<30 and cp[-1] > ma[-1]:
                sig = Sig("STOCH_FAST_OPEN",now['snapshotTime'],"BUY",4,comment="stars have aligned 30 min",life=1)
                super().add_signal(sig,market)
                
            if detect.crossunder(stoch_k,stoch_d) and max(stoch_k[-5:])>70 and cp[-1] < ma[-1]:
                sig = Sig("STOCH_FAST_OPEN",now['snapshotTime'],"SELL",4,comment="stars have aligned 30 min",life=1)
                super().add_signal(sig,market)

            

            
                
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
        # try:
        #     for s in [x for x in self.signals if x.market == market.epic and "SLOW" in x.name]:
        #         if not s.process():
        #             print("{} timed out".format(s.name))
        #             self.signals.remove(s)

        #     if 'MINUTE_30' not in market.prices:
        #         return

        #     # maindir = self.maindir(market,"DAY")
        #     prices = market.prices['MINUTE_30']

        #     ma = ta.ma(20,prices)
        #     cp = [x['closePrice']['mid'] for x in prices]
        #     stoch_k, stoch_d = ta.stochastic(prices,5,3,3)


        #     now = prices[-1]
        #     if detect.crossover(cp,ma) and min(stoch_k[-7:])<20:
        #         sig = Sig("STOCH_SLOW_OPEN",now['snapshotTime'],"BUY",4,comment="stars have aligned 30 min",life=1)
        #         super().add_signal(sig,market)
                
        #     if detect.crossunder(cp,ma) and max(stoch_k[-7:])>80:
        #         sig = Sig("STOCH_SLOW_OPEN",now['snapshotTime'],"SELL",4,comment="stars have aligned 30 min",life=1)
        #         super().add_signal(sig,market)

            

            
                
        # except Exception as e:
        #     exc_type, exc_obj, exc_tb = sys.exc_info()
        #     fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        #     logger.info("{} live fail".format(market.epic))
        #     logger.info(exc_type)
        #     logger.info(fname)
        #     logger.info(exc_tb.tb_lineno)
        #     logger.info(exc_obj)
        #     pass

    
    def assess_close(self,signal,trade):
        pass
        # if signal.name=="MFI_SLOW" and "SLOW" in trade.prediction['signal']['name']:
        #     trade.log_status("Opposing MFI slow signal found - close!")
        #     trade.close_trade()

    