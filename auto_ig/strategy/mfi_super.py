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

class mfi_super(Strategy):
    """
    """

    def __init__(self, mfi_length= 14, smooth = 9, smoother=5):
        name = "mfi_super"
        super().__init__(name)
        self.mfi_length = mfi_length
        self.smooth = smooth
        self.smoother = smoother


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
        stop = math.ceil((dayatr[-1] / 2) + (market.spread*2))
        limit = math.ceil(atr[-1]*2)

        limit = min(limit,28)
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

            dirday = self.maindir(market,"DAY")
            dir30 = self.maindir(market,"MINUTE_30")
            prices = market.prices['MINUTE_5']

            mfi = ta.mfi_super(prices,self.mfi_length,self.smooth)
            smoother = ta.ma(self.smoother,prices,values=mfi,name="super_mfi_smoothed")

            # try to find peaks in the smoothed data
            now = prices[-1]
            if dirday=="BUY" and dir30=="BUY":
                minsmooth = min(smoother[-3:])
                if minsmooth < 20 and minsmooth==smoother[-2]:
                    sig = Sig("MFI_SUPER_FAST_OPEN",now['snapshotTime'],"BUY",4,comment="market is going up",life=0)
                    super().add_signal(sig,market)
            
            if dirday=="SELL" and dir30=="SELL":
                maxsmooth = max(smoother[-3:])
                if maxsmooth > 80 and maxsmooth==smoother[-2]:
                    sig = Sig("MFI_SUPER_FAST_OPEN",now['snapshotTime'],"SELL",4,comment="market is going up",life=0)
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
        

    def maindir(self,market, res):
        direction = "NONE"

        prices = market.prices[res]

        wma5 = ta.wma(5,prices)
        wma14 = ta.wma(14,prices)
        wma28 = ta.wma(28,prices)

        wma5_delta = wma5[-1] - wma5[-2]
        wma14_delta = wma14[-1] - wma14[-2]
        wma28_delta = wma28[-1] - wma28[-2]

        if wma5_delta > 0 and wma14_delta > 0 and wma28_delta > 0:
            direction = "BUY"
        
        if wma5_delta < 0 and wma14_delta < 0 and wma28_delta < 0:
            direction = "SELL"

        market.data['mfi super wma5 {}'.format(res)] = wma5_delta
        market.data['mfi super wma14 {}'.format(res)] = wma14_delta
        market.data['mfi super wma28 {}'.format(res)] = wma28_delta
        
        market.data['mfi super direction'] = direction
        return direction
    
    def getdir(self,market,res,wmaperiod,mfiperiod,mfismooth):
        direction = "NONE"

        prices = market.prices[res]

        mfi = ta.mfi(prices,mfiperiod)
        sm = ta.ma(mfismooth,prices,values=mfi,name="sma_mfi_{}".format(mfiperiod))
        sm_delta = sm[-1] - sm[-2]
        wma = ta.wma(wmaperiod,prices)

        wma_delta = wma[-1] - wma[-2]

        if sm_delta>0 and wma_delta > 0:
            direction = "BUY"
        elif sm_delta < 0 and wma_delta < 0:
            direction = "SELL"
        else:
            direction = "NONE"

        return direction


    def assess_close(self,signal,trade):
        pass
        # if signal.name=="MFI_SLOW" and "SLOW" in trade.prediction['signal']['name']:
        #     trade.log_status("Opposing MFI slow signal found - close!")
        #     trade.close_trade()

    