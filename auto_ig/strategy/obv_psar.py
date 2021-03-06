import logging
import os,sys
from numbers import Number
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

    def __init__(self, obv_smooth = 14, obv_fast=7):
        name = "obv_psar"
        super().__init__(name)
        self.obv_smooth = obv_smooth
        self.obv_fast = obv_fast

    def prediction(self, signal,market,resolution):
        """default stoploss and limit calculator based on atr_5"""
        prices = market.prices['MINUTE_30']
        atr, tr = ta.atr(14,prices)
        low_range = min(tr)
        max_range = max(tr)
        
        stop = (atr[-1] * 1.5) + (market.spread*2)
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
            "limit_distance" : stop/2,
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
                    
                    self.signals.remove(s)

            if 'MINUTE_5' not in market.prices:
                return

            prices = market.prices['MINUTE_5']
            
            # check longer term and day-ish trend
            day_wma = ta.wma(5,market.prices['DAY'])
            day_psar = ta.psar(market.prices['DAY'],0.01,0.2)
            roc = ta.roc(36,market.prices['MINUTE_30'])
            now_day = market.prices['DAY'][-1]
            day_psar_dir = "BUY"
            if isinstance(now_day['psar_bear'], Number):
                day_psar_dir = "SELL"

            # want to look at the daily trends before even considering opening a position
            daydir = "NONE"
            wma_delta = day_wma[-1] - day_wma[-2]

            # also look at the 30 min trends
            min30obv = ta.obv(market.prices['MINUTE_30'],10)
            min30obvma = ta.wma(5, prices = market.prices['MINUTE_30'], values = min30obv, name="obv_wma")
            min30psar = ta.psar(market.prices['MINUTE_30'],0.03,0.2)
            min30wma = ta.wma(25,market.prices['MINUTE_30'])

            # do some 30 min checks
            now30 = market.prices['MINUTE_30'][-1]
            prev30 = market.prices['MINUTE_30'][-2]
            
            min30wma_delta = min30wma[-1] - min30wma[-2]

            dir30 = "BUY"
            if isinstance(now30['psar_bear'], Number):
                dir30 = "SELL"
            roc_delta = roc[-1] - roc[-2]
            market.data['wma_delta'] = wma_delta
            market.data['30 min psar'] = dir30
            market.data['min30obvma'] = min30obvma[-1]
            market.data['day_psar'] = day_psar_dir


            if day_psar_dir == "BUY" and wma_delta > 0 and min30wma_delta > 0 and dir30=="BUY" and min30obvma[-1] > 0:
                daydir = "BUY"
            
            if day_psar_dir == "SELL" and wma_delta < 0 and min30wma_delta < 0 and dir30=="SELL" and min30obvma[-1] < 0:
                daydir = "SELL"

            flip30 = self.psar_flip(now30,prev30)

            
            

            obv = ta.obv(prices,self.obv_smooth)
            obv_ma = ta.wma(self.obv_fast,prices = prices,values=obv, name="obv_wma")
            psar = ta.psar(prices,0.03,0.2)
            now = prices[-1]
            prev = prices[-2]
            
            # check if min 30 has flipped PSAR, create a close signal
            # TODO: make an open signal if current 5 mins are looking good already
            
            if flip30:
                score = 2
                com = "MIN 30 PSAR flip - CLOSE"
                if daydir=="BUY" and obv_ma[-1] > 0 and isinstance(now['psar_bull'],Number):
                    score = 4
                    com = "MIN 30 PSAR flip - OPEN"
                    sig = Sig("PSAR_30_FLIP",now30['snapshotTime'],flip30,4,comment = com,life=1)

                    super().add_signal(sig,market)
                    
                if daydir=="SELL" and obv_ma[-1] < 0 and isinstance(now['psar_bear'],Number):
                    score = 4
                    com = "MIN 30 PSAR flip - OPEN"
                    sig = Sig("PSAR_30_FLIP",now30['snapshotTime'],flip30,4,comment = com,life=1)

                    super().add_signal(sig,market)

                

            # check for obv_ma crossovers
            if detect.crossover(obv_ma,0):
                if daydir=="BUY" and isinstance(now['psar_bull'],Number):
                    sig = Sig("OBV_OPEN",now['snapshotTime'],"BUY",4,comment = "ZERO_CROSS",life=1)
                
                    super().add_signal(sig,market)

            if detect.crossunder(obv_ma,0):
                if daydir=="SELL" and isinstance(now['psar_bear'],Number):
                    sig = Sig("OBV_OPEN",now['snapshotTime'],"SELL",4,comment = "ZERO_CROSS",life=1)
                
                    super().add_signal(sig,market)

            # now check for flip events
            flip5 = self.psar_flip(now,prev)
            market.data['flip5'] = flip5

            if flip5=="BUY" and daydir=="BUY" and obv_ma[-1] > 0:
                sig = Sig("PSAR_OPEN",now['snapshotTime'],"BUY",4,comment = "PSAR_FLIP",life=1)
                super().add_signal(sig,market)
            
            if flip5=="SELL" and daydir=="SELL" and obv_ma[-1] < 0:
                sig = Sig("PSAR_OPEN",now['snapshotTime'],"SELL",4,comment = "PSAR_FLIP",life=1)
                super().add_signal(sig,market)


            # now check for 3 period PSAR event
            # if self.is_psar_type("psar_bull",prices[-2],prices[-3],prices[-4]) and self.is_psar_type("psar_bear",prices[-5]):
            #     sig = Sig("PSAR_CLOSE",now['snapshotTime'],"BUY",2,comment="3 conflicting psar dots", life=1)
            #     super().add_signal(sig,market)
            # if self.is_psar_type("psar_bear",prices[-2],prices[-3],prices[-4]) and self.is_psar_type("psar_bull",prices[-5]):
            #     sig = Sig("PSAR_CLOSE",now['snapshotTime'],"SELL",2,comment="3 conflicting psar dots", life=1)
            #     super().add_signal(sig,market)
                
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
        if signal.name=="PSAR_30_FLIP":
            trade.log_status("PSAR 30 flipped CLOSE!")
            trade.close_trade()
        if signal.name=="PSAR_CLOSE":
            trade.log_status("3 periods flipped CLOSE!")
            trade.close_trade()

        if signal.name == "OBV_CLOSE" and trade.pip_diff>0:
            trade.log_status("obv crossed back and in profit")
            trade.close_trade()

    def is_psar_type(self,typename,*times):
        ret_val = True
        for t in times:
            if not isinstance(t[typename],Number):
                ret_val = False
        return ret_val

    def psar_flip(self,now,prev):
        if isinstance(now['psar_bull'],Number) and not isinstance(prev['psar_bull'],Number):
            return "BUY"
        if isinstance(now['psar_bear'],Number) and not isinstance(prev['psar_bear'],Number):
            return "SELL"
        
        return False
    
   
    

