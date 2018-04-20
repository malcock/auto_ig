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

    def __init__(self, mfi_period= 14, ma_len = 40):
        name = "mfi"
        super().__init__(name)
        self.mfi_period = mfi_period
        self.ma_len = ma_len


    def prediction(self, signal,market,resolution):
        """default stoploss and limit calculator based on atr_14"""
        res = 'MINUTE_30'
        if "SLOW" in signal.name:
            res = "DAY"
        prices = market.prices['MINUTE_30']
        atr, tr = ta.atr(14,prices)
        low_range = min(tr)
        max_range = max(tr)
        
        stop = math.ceil((atr[-1] * 1.5) + (market.spread*2))
        limit = math.ceil(stop/2)
        if "SLOW" in signal.name:
            stop = math.ceil((atr[-1] * 0.5) + (market.spread*2))
            limit = math.ceil(stop*0.75)

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

    def match_lens(self,a,b):
        diff = len(a) - len(b)
        if diff==0:
            return a,b
        elif diff>0:
            a = a[-diff:]
        else:
            b = b[diff:]
        return a,b

    def fast_signals(self,market,prices,resolution):
        
        try:
            for s in [x for x in self.signals if x.market == market.epic and "FAST" in x.name]:
                if not s.process():
                    print("{} timed out".format(s.name))
                    self.signals.remove(s)

            if 'MINUTE_5' not in market.prices:
                return

            prices = market.prices['MINUTE_5']

            mfi = ta.mfi(prices,self.mfi_period)
            ma = ta.wma(self.ma_len,prices)
            
            now = prices[-1]
            # detect crossovers
            if detect.crossunder(mfi,80):
                sig = Sig("MFI_FAST",now['snapshotTime'],"SELL",1,comment = "crossed back from overbought {}".format(mfi[-1]),life=8)
                super().add_signal(sig,market)
            if detect.crossover(mfi,20):
                sig = Sig("MFI_FAST",now['snapshotTime'],"BUY",1,comment = "crossed back from overbought {}".format(mfi[-1]),life=8)
                super().add_signal(sig,market)

            open_sigs = [x for x in self.signals if x.name=="MFI_FAST" and x.market==market.epic]
            for s in open_sigs:
                cp = now['closePrice']['mid']
                if s.position=="BUY":
                    # looking for close above
                    if cp>ma[-1]:
                        sig = Sig("MFI_FAST_OPEN",now['snapshotTime'],"BUY",4,comment = "crossed over ma {} {}".format(cp,ma[-1]),life=4)
                else:
                    if cp<ma[-1]:
                        sig = Sig("MFI_FAST_OPEN",now['snapshotTime'],"SELL",4,comment = "crossed under ma {} {}".format(cp,ma[-1]),life=4)
            
            
                
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
        try:
            for s in [x for x in self.signals if x.market == market.epic and "SLOW" in x.name]:
                if not s.process():
                    print("{} timed out".format(s.name))
                    self.signals.remove(s)


            mfi = ta.mfi(prices,self.mfi_period)
            ma = ta.wma(self.ma_len,prices)
            
            now = prices[-1]
            # detect crossovers
            if detect.crossunder(mfi,70):
                sig = Sig("MFI_SLOW",now['snapshotTime'],"SELL",2,comment = "crossed back from overbought {}".format(mfi[-1]),life=8)
                super().add_signal(sig,market)
            if detect.crossover(mfi,30):
                sig = Sig("MFI_SLOW",now['snapshotTime'],"BUY",2,comment = "crossed back from overbought {}".format(mfi[-1]),life=8)
                super().add_signal(sig,market)

            open_sigs = [x for x in self.signals if x.name=="MFI_SLOW" and x.market==market.epic]
            for s in open_sigs:
                cp = now['closePrice']['mid']
                if s.position=="BUY":
                    # looking for close above
                    if cp>ma[-1]:
                        sig = Sig("MFI_SLOW_OPEN",now['snapshotTime'],"BUY",4,comment = "crossed over ma {} {}".format(cp,ma[-1]),life=4)
                else:
                    if cp<ma[-1]:
                        sig = Sig("MFI_SLOW_OPEN",now['snapshotTime'],"SELL",4,comment = "crossed under ma {} {}".format(cp,ma[-1]),life=4)
        
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info("{} live fail".format(market.epic))
            logger.info(exc_type)
            logger.info(fname)
            logger.info(exc_tb.tb_lineno)
            logger.info(exc_obj)
            pass

        
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
    
   
    

