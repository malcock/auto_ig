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

class obv_psar(Strategy):

    def __init__(self, obv_smooth, obv_fast):
        name = "obv_psar"
        super().__init__(name)
        self.obv_smooth = obv_smooth
        self.obv_fast = obv_fast

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
            "limit_distance" : 5,
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
            
            # check longer term and day-ish trend
            day_wma25 = ta.wma(25,market.prices['DAY'])
            roc = ta.roc(36,market.prices['MINUTE_30'])

            # want to look at the daily trends before even considering opening a position
            daydir = "NONE"
            wma_delta = day_wma25[-1] - day_wma25[-2]
            if wma_delta > 0 and roc[-1] > 0:
                daydir = "BUY"
            
            if wma_delta < 0 and roc[-1] < 0:
                daydir = "SELL"

   
            obv = ta.obv(prices,self.obv_smooth)
            obv_ma = ta.wma(self.obv_fast,prices = prices,values=obv, name="obv_wma")
            psar = ta.psar(prices)
            now = prices[-1]
            prev = prices[-2]

            if daydir =="BUY":
                # detect a crossover in a bull
                if now['psar_bull'] != '':
                    if detect.crossover(obv_ma,0):
                        # open position i guess
                        sig = Sig("PSAR_OPEN",now['snapshotTime'],"BUY",4,comment = "ZERO_CROSS",life=1)
                        super().add_signal(sig,market)
                
                if now['psar_bull'] != '' and prev['psar_bull']== '' and obv_ma[-1] >0:
                    sig = Sig("PSAR_OPEN",now['snapshotTime'],"BUY",4,comment = "PSAR_FLIP",life=1)
                    super().add_signal(sig,market)
            else:
                if now['psar_bear'] != '':
                    if detect.crossunder(obv_ma,0):
                        # open position i guess
                        sig = Sig("PSAR_OPEN",now['snapshotTime'],"SELL",4,comment = "ZERO_CROSS",life=1)
                        super().add_signal(sig,market)
                
                if now['psar_bear'] != '' and prev['psar_bear']== '' and obv_ma[-1] < 0:
                    sig = Sig("PSAR_OPEN",now['snapshotTime'],"SELL",4,comment = "PSAR_FLIP",life=1)
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
        



    
   
    

