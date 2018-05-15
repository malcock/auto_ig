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

class linreg(Strategy):
    """
    """

    def __init__(self):
        name = "linreg"
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
        SL_MULTIPLIER = 4
        LOW_SL_WATERMARK = 10
        HIGH_SL_WATERMARK = 90
        res = 'MINUTE_5'
        if "SLOW" in signal.name:
            res = "MINUTE_30"
        prices = market.prices[res][-14:]
        atr, tr = ta.atr(14,prices)
        low_range = min(tr)
        max_range = max(tr)
        stop = max_range

        if int(stop) <= LOW_SL_WATERMARK or int(stop) >= HIGH_SL_WATERMARK:
            logger.info("Crazy SL - NO")
            return
        # limit = math.ceil(atr[-1]*1.25)

        if signal.position == "BUY":
            lows = [x['lowPrice']['mid'] for x in prices]
            limit = int(abs(float(min(lows)) - float(market.bid)) / SL_MULTIPLIER)
            # GO LONG
            DIRECTION_TO_TRADE = "BUY"
            DIRECTION_TO_CLOSE = "SELL"
            DIRECTION_TO_COMPARE = 'bid'
            # low = min([x['lowPrice']['bid'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(self.bid - low)
            # stop = abs(self.bid - self.prices[signal.resolution][-2]['lowPrice']['bid'])

        else:
            # GO SHORT!
            highs = [x['highPrice']['mid'] for x in prices]
            limit = int(abs(float(max(highs)) - float(market.bid)) / SL_MULTIPLIER)
            DIRECTION_TO_TRADE = "SELL"
            DIRECTION_TO_CLOSE = "BUY"
            DIRECTION_TO_COMPARE = 'offer'
            # high = max([x['highPrice']['ask'] for x in self.prices[signal.resolution][:-5]])
            # stop = abs(high - self.offer)
            # stop = abs(self.prices[signal.resolution][-2]['highPrice']['ask'] - self.offer)

        limit = min(limit,5)
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

    

    def slow_signals(self,market,prices,resolution):
        self.fast_signals(market,prices,resolution)
        pass
  
    

    def fast_signals(self,market,prices, resolution):
        
        def distance(a, b):
            if (a == b):
                return 0
            elif (a < 0) and (b < 0) or (a > 0) and (b > 0):
                if (a < b):
                    return (abs(abs(a) - abs(b)))
                else:
                    return -(abs(abs(a) - abs(b)))
            else:
                return math.copysign((abs(a) + abs(b)), b)
        try:
            for s in [x for x in self.signals if x.market == market.epic and "FAST" in x.name]:
                if not s.process():
                    
                    self.signals.remove(s)

            if 'MINUTE_30' not in market.prices:
                return
            
            isgood = self.isgood(market)
            print("{} is good {}".format(market.epic,isgood))
            if isgood=="OK":
                prices = market.prices['MINUTE_30'][-16:]
                m,c = ta.linreg(prices)

                stoch_k,stoch_d = ta.stochastic(prices,5,3,3)
                rsi = ta.rsi(14,prices)
                rsima = ta.ma(9,prices,values=rsi,name="rsi_ma_9")

                now = prices[-1]
                if distance(market.bid,c)>1:
                    sig = Sig("LINREG_SLOW_OPEN",now['snapshotTime'],"SELL",4,comment="market is going down",life=0)
                    super().add_signal(sig,market)
                elif distance(market.bid,c) < -1:
                    sig = Sig("LINREG_SLOW_OPEN",now['snapshotTime'],"BUY",4,comment="market is going up",life=0)
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
        

    def isgood(self,market):

        direction = "NONE"


        time_now = datetime.datetime.time(datetime.datetime.now(timezone('GB')).replace(tzinfo=None))
        
        allowed_epics = []
        if (datetime.time(7,00) < time_now < datetime.time(16,00)):
            allowed_epics.append("GBP")
            allowed_epics.append("EUR")
        if (datetime.time(12,00) <= time_now <= datetime.time(21,00)):
            allowed_epics.append("USD")
        if (time_now >= datetime.time(22,00) or time_now <= datetime.time(7,00)):
            allowed_epics.append("AUD")
        if (time_now >= datetime.time(23,00) or time_now <= datetime.time(8,00)):
            allowed_epics.append("JPY")
        
        print(allowed_epics)
        if any(x in market.epic for x in allowed_epics):
            direction="OK"

        market.data['linreg open'] = direction
        return direction
    

    def assess_close(self,signal,trade):
        pass
        # if signal.name=="MFI_SLOW" and "SLOW" in trade.prediction['signal']['name']:
        #     trade.log_status("Opposing MFI slow signal found - close!")
        #     trade.close_trade()

    