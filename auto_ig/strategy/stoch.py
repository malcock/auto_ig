import logging
import os,sys
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

    def __init__(self,stoch_len=14,k_smooth=3,d_smooth=3):
        name = "stoch"
        super().__init__(name)
        self.stoch = stoch_len
        self.ksmooth = k_smooth
        self.dsmooth = d_smooth

    def backfill(self,market,resolution,lookback=10):
        if 'MINUTE_5' in market.prices:
            prices = market.prices['MINUTE_5']
            price_len = len(prices)
            if price_len - lookback > 40:

                for i in list(range(lookback,-1,-1)):
                    p = price_len - i
                    ps = prices[:p]
                    self.fast_signals(market,ps,'MINUTE_5')
    
    def prediction(self, signal,market,resolution):
        """default stoploss and limit calculator based on atr_5"""
        prices = market.prices['MINUTE_5']
        atr, tr = ta.atr(14,prices)
        low_range = min(tr)
        max_range = max(tr)
        
        stop = math.ceil((atr[-1] * 2) + (market.spread*1.5))
        limit = math.ceil(atr[-1] * 3)
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
            market.data['maindir_30'] = maindir
            prices = market.prices['MINUTE_5']

            stoch_k,stoch_d = ta.stochastic(prices,14,3,3)
            ma = ta.wma(40,prices)

            now = prices[-1]
            cp = [x['closePrice']['mid'] for x in prices]

            if detect.crossover(cp,ma) and maindir=="BUY":
                mink = min(stoch_k[-8:])
                
                if mink<25 and stoch_k[-1]>mink:
                    
                    sig = Sig("STOCH_FAST_OPEN",now['snapshotTime'],"BUY",4,comment="5 min price crossed over ma and low stoch",life=2)
                    self.add_signal(sig,market)
            
            if detect.crossunder(cp,ma) and maindir=="SELL":
                maxk = max(stoch_k[-8:])
                
                if maxk>75 and stoch_k[-1]<maxk:
                    
                    sig = Sig("STOCH_FAST_OPEN",now['snapshotTime'],"SELL",4,comment="5 min price crossed under ma and high stoch",life=2)
                    self.add_signal(sig,market)
            

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
        
    def assess_close(self,signal,trade):
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


    
   