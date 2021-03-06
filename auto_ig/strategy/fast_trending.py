import logging
import os,sys
from numbers import Number
import math
import datetime
from pytz import timezone
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
 
class fast_trending(Strategy):
    """Creates open signals 
        - checking for MFI cross back from 25 or 75
            - create a signal that lasts 8 periods
        - open long when mfi cross back from <25
            - if close price > ema40
        - open short when mfi cross back from >75
            - if close price < ema40
    """
 
    def __init__(self):
        name = "fast_trending"
        super().__init__(name)
 
 
        self.last_state = "NONE"

        self.resolutions['MINUTE_5'] = self.fast
        # self.resolutions['HOUR'] = self.h4

        self.atrs = {}

    
 
    # def backfill(self,market,resolution,lookback=18):
        
    #     print("backtesting slow sigs")
    #     prices = market.prices['MINUTE_30']
    #     price_len = len(prices)
    #     print(price_len - lookback)
    #     if price_len - lookback < 100:
 
    #         for i in list(range(lookback,-1,-1)):
    #             p = price_len - i
    #             ps = prices[:p]
    #             print("{} {}".format(market.epic, ps[-1]['snapshotTime']))
    #             self.slow_signals(market,ps,'MINUTE_30')
 
    #     print("backtesting fast sigs")
    #     prices = market.prices['MINUTE_5']
    #     price_len = len(prices)
    #     print(price_len - lookback)
    #     if price_len - lookback < 100:
 
    #         for i in list(range(lookback,-1,-1)):
    #             p = price_len - i
    #             ps = prices[:p]
    #             print("{} {}".format(market.epic, ps[-1]['snapshotTime']))
    #             self.fast_signals(market,ps,'MINUTE_5')

    def prediction(self, signal,market,resolution):
        """default stoploss and limit calculator based on atr_14"""

        prices = market.prices[resolution]
        atr, tr = ta.atr(14,prices)
        low_range = min(tr)
        max_range = max(tr)
 
        
        stop = (atr[-1]) + (market.spread*2)
        limit = -1
 
        # limit = max(limit,4)
        # limit = min(7,limit)
        if signal.position == "BUY":
            # GO LONG
            # lows = [x['lowPrice']['mid'] for x in prices[-5:]]
            # stop = market.bid - min(lows)
            DIRECTION_TO_TRADE = "BUY"
            DIRECTION_TO_CLOSE = "SELL"
            DIRECTION_TO_COMPARE = 'bid'
            # low = min([x['lowPrice']['bid'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(self.bid - low)
            # stop = abs(self.bid - self.prices[signal.resolution][-2]['lowPrice']['bid'])
 
        else:
            # GO SHORT!
            # highs = [x['highPrice']['mid'] for x in prices[-5:]]
            # stop = max(highs) - market.offer
            DIRECTION_TO_TRADE = "SELL"
            DIRECTION_TO_CLOSE = "BUY"
            DIRECTION_TO_COMPARE = 'offer'
            # high = max([x['highPrice']['ask'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(high - self.offer)
            # stop = abs(self.prices[signal.resolution][-2]['highPrice']['ask'] - self.offer)
 
        # stop =  math.ceil(stop + (market.spread*2))
        # if stop<=market.spread*2:
        #     stop = market.spread*3
        # stop = min(stop,50)
        
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
                "resolution":signal.resolution,
                "comment" : signal.comment
            }
            
        }
 
        return prediction_object


    def fast(self,market,prices,resolution):
        try:
            if len(prices)<100:
                logger.warning("{} {} need more data".format(market.epic,resolution))
                return
            if market.epic not in self.atrs:
                self.atrs[market.epic] = {}
            
            self.atrs[market.epic][resolution],tr = ta.atr(14,prices)
            
            print("HEY YO")
            trend = ta.ema(100,prices)

            # bb_u,bb_l,ma = ta.bollinger_bands(20,2,prices)

            ma = ta.ma(20,prices)

            ema = ta.ema(5,prices)
            now = prices[-1]
            if detect.crossover(ema,ma) and ma[-1] > trend[-1]:
                sig = Sig(market,"OPEN",now['snapshotTime'],"BUY",4,resolution,comment="crossover matches trend",life=1)
                super().add_signal(sig,market)

            if detect.crossunder(ema,ma) and ma[-1] < trend[-1]:
                sig = Sig(market,"OPEN",now['snapshotTime'],"SELL",4,resolution,comment="crossunder matches trend",life=1)
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
        


    def trailing_stop(self,trade):
        res = trade.prediction['signal']['resolution']
        use_trail = True if res in ['MINUTE_5'] else False
        stop_val = 0
        if use_trail:
            if trade.market.epic not in self.atrs:
                self.atrs[trade.market.epic] = {}
                self.atrs[trade.market.epic][res],tr = ta.atr(14,trade.market.prices[res])
            atr_now = self.atrs[trade.market.epic][res][-1]
            stop_val = trade.pip_max - atr_now
            if trade.pip_max < atr_now*1.5:
                use_trail = False
            

        return use_trail,stop_val



        
    

    def assess_close(self,signal,trade):
        pass


        