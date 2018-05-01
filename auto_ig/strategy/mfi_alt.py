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

class mfi_alt(Strategy):
    """Creates open signals 
        - checking for MFI cross back from 25 or 75
            - create a signal that lasts 8 periods
        - open long when mfi cross back from <25
            - if close price > ema40
        - open short when mfi cross back from >75
            - if close price < ema40
    """

    def __init__(self, slow_mfi= 14, fast_mfi = 9, smooth_slow = 12, smooth_fast = 9):
        name = "mfi_alt"
        super().__init__(name)
        self.slow_mfi = slow_mfi
        self.fast_mfi = fast_mfi
        self.smooth_slow = smooth_slow
        self.smooth_fast = smooth_fast

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
        
        stop = math.ceil((atr[-1] * 2) + (market.spread*2))
        limit = math.ceil(atr[-1] *1.5)

        limit = min(limit,16)
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

            maindir = self.maindir(market,"MINUTE_30")
            prices = market.prices['MINUTE_5']

            mfi = ta.mfi(prices,self.fast_mfi)
            ma = ta.ma(self.smooth_fast,prices,values=mfi,name="sma_mfi_{}".format(self.fast_mfi))
            
            now = prices[-1]

            # detect ma crosses
            if detect.crossover(ma,50) and maindir=="BUY":
                sig = Sig("MFI_ALT_FAST_OPEN",now['snapshotTime'],"BUY",4,comment="5min price crossed over ma", life=2)
                super().add_signal(sig,market)
            
            if detect.crossunder(ma,50) and maindir=="SELL":
                sig = Sig("MFI_ALT_FAST_OPEN",now['snapshotTime'],"SELL",4,comment="5min price crossed under ma", life=2)
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
        

    def maindir(self,market,res,include_price_delta=False):
        direction = "NONE"
        prices = market.prices[res]
        
        mfi = ta.mfi(prices,self.slow_mfi)
        sm = ta.ma(self.smooth_slow,prices,values=mfi,name="sma_mfi_{}".format(self.slow_mfi))

        sm_delta = sm[-1] - sm[-2]

        if sm_delta>0:
            direction = "BUY"
        else:
            direction = "SELL"

        return direction
        
    def assess_close(self,signal,trade):
        pass
        # if signal.name=="MFI_SLOW" and "SLOW" in trade.prediction['signal']['name']:
        #     trade.log_status("Opposing MFI slow signal found - close!")
        #     trade.close_trade()

    