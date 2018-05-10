import logging
import os,sys
import datetime
from numbers import Number
import math
from .. import indicators as ta
from .. import detection as detect
from .base import Strategy, Sig
from pytz import timezone


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

class simple(Strategy):
    """Creates open signals 
        - checking for MFI cross back from 25 or 75
            - create a signal that lasts 8 periods
        - open long when mfi cross back from <25
            - if close price > ema40
        - open short when mfi cross back from >75
            - if close price < ema40
    """

    def __init__(self, slow_mfi= 12, smooth_slow = 6):
        name = "simple"
        super().__init__(name)
        self.slow_mfi = slow_mfi
        self.smooth_slow = smooth_slow

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
        dayatr,tr = ta.atr(14,market.prices['DAY'])
        stop = math.ceil((atr[-1]) + (market.spread*2))
        limit = math.ceil(atr[-1]*1.25)

        limit = min(limit,8)
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

            maindir = self.maindir(market)
            prices = market.prices['MINUTE_5']

            ema = ta.ema(5,prices)
            ema_delta = ema[-1] - ema[-2]

            
            now = prices[-1]
            
            if ema_delta > 0 and maindir=="BUY":
                sig = Sig("SIMPLE_FAST_OPEN",now['snapshotTime'],"BUY",4,comment="market is going up",life=0)
                super().add_signal(sig,market)
            elif ema_delta < 0 and maindir=="SELL":
                sig = Sig("SIMPLE_FAST_OPEN",now['snapshotTime'],"SELL",4,comment="market is going down",life=0)
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
        

    def maindir(self,market):

        direction = "NONE"
        prices = market.prices['DAY']

        
        
        ema = ta.ema(3,prices)
        
        ema_delta = ema[-1] - ema[-2]

        if ema_delta>0 and market.net_change > 0:
            direction="BUY"
        elif ema_delta <0 and market.net_change<0:
            direction="SELL"

        time_now = datetime.datetime.time(datetime.datetime.now(timezone('GB')).replace(tzinfo=None))
        
        if (datetime.time(7,00) < time_now < datetime.time(15,00)) and "EUR" not in market.epic:
            direction+=" - out of hours"
        if (datetime.time(7,00) < time_now < datetime.time(16,00))  and "GBP" not in market.epic:
            direction+=" - out of hours"
        if (datetime.time(12,00) < time_now < datetime.time(21,00))  and "USD" not in market.epic:
            direction+=" - out of hours"
        if (time_now >= datetime.time(22,00) or time_now <= datetime.time(7,00)) and "AUD" not in market.epic:
            direction+=" - out of hours"
        if (time_now >= datetime.time(23,00) or time_now <= datetime.time(8,00)) and "JPY" not in market.epic:
            direction+=" - out of hours"

        market.data['simple dir'] = direction
        return direction
    

    def assess_close(self,signal,trade):
        pass
        # if signal.name=="MFI_SLOW" and "SLOW" in trade.prediction['signal']['name']:
        #     trade.log_status("Opposing MFI slow signal found - close!")
        #     trade.close_trade()

    