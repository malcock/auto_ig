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

class mfi(Strategy):
    """Creates open signals 
        - checking for MFI cross back from 25 or 75
            - create a signal that lasts 8 periods
        - open long when mfi cross back from <25
            - if close price > ema40
        - open short when mfi cross back from >75
            - if close price < ema40
    """

    def __init__(self, slow_mfi= 9, fast_mfi = 9, ma_len = 40):
        name = "mfi"
        super().__init__(name)
        self.slow_mfi = slow_mfi
        self.fast_mfi = fast_mfi
        self.ma_len = ma_len

    def backfill(self,market,resolution,lookback=10):
        prices = market.prices['MINUTE_30']
        price_len = len(prices)
        if price_len - lookback > 50:

            for i in list(range(lookback,-1,-1)):
                p = price_len - i
                ps = prices[:p]
                self.slow_signals(market,ps,'MINUTE_30')
        
        prices = market.prices['MINUTE_5']
        price_len = len(prices)
        if price_len - lookback > 50:

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
        limit = math.ceil(stop*2)
        if "SLOW" in signal.name:
            stop = math.ceil((atr[-1] * 1.5) + (market.spread*2))
            limit = math.ceil(stop*1.75)

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

            mfi = ta.mfi(prices,self.slow_mfi)
            ma = ta.wma(self.ma_len,prices)
            
            now = prices[-1]
            cp = [x['closePrice']['mid'] for x in prices]
            # detect ma crosses
            if detect.crossover(ma,cp) and maindir=="BUY":
                # get the previous mfi points to see if we've been under mfi threshold
                minmfi = min(mfi[-6:])
                if minmfi<30 and mfi[-1]>minmfi:
                    sig = Sig("MFI_FAST_OPEN",now['snapshotTime'],"BUY",4,comment="5min price crossed over ma", life=2)
                    super().add_signal(sig,market)
            
            if detect.crossunder(ma,cp) and maindir=="SELL":
                maxmfi = max(mfi[-6:])
                if maxmfi>70 and mfi[-1]<maxmfi:
                    sig = Sig("MFI_FAST_OPEN",now['snapshotTime'],"SELL",4,comment="5min price crossed under ma", life=2)
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
        if resolution in ["DAY","MINUTE_5"]:
            return
        try:
            for s in [x for x in self.signals if x.market == market.epic and "SLOW" in x.name]:
                if not s.process():
                    print("{} timed out".format(s.name))
                    self.signals.remove(s)
                
            maindir = self.maindir(market,"DAY")

            mfi = ta.mfi(prices,self.slow_mfi)
            ma = ta.wma(self.ma_len,prices)
            
            now = prices[-1]
            cp = [x['closePrice']['mid'] for x in prices]
            # detect ma crosses
            if detect.crossover(ma,cp) and maindir=="BUY":
                # get the previous mfi points to see if we've been under mfi threshold
                minmfi = min(mfi[-8:])
                if minmfi<30 and mfi[-1]>minmfi:
                    sig = Sig("MFI_SLOW_OPEN",now['snapshotTime'],"BUY",4,comment="30 min price crossed over ma", life=2)
                    super().add_signal(sig,market)
            
            if detect.crossunder(ma,cp) and maindir=="SELL":
                maxmfi = max(mfi[-8:])
                if maxmfi>70 and mfi[-1]<maxmfi:
                    sig = Sig("MFI_SLOW_OPEN",now['snapshotTime'],"SELL",4,comment="30min price crossed under ma", life=2)
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

    def maindir(self,market,res,include_price_delta=False):
        direction = "NONE"
        prices = market.prices[res]
        wma = ta.wma(5,prices)
        wma_delta = wma[-1] - wma[-2]
        price_delta = prices[-1]['closePrice']['mid'] - prices[-2]['closePrice']['mid']

        if wma_delta>0:
            direction="BUY"
        elif wma_delta<0:
            direction="SELL"
        else:
            direction="NONE"
        
        if include_price_delta:
            if direction=="BUY" and price_delta<0:
                direction = "NONE"
            elif direction=="SELL" and price_delta>0:
                direction="NONE"

        return direction
        
    def assess_close(self,signal,trade):
        pass
        # if signal.name=="MFI_SLOW" and "SLOW" in trade.prediction['signal']['name']:
        #     trade.log_status("Opposing MFI slow signal found - close!")
        #     trade.close_trade()

    