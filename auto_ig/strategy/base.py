import logging
# from ..sig import Sig
from .. import indicators as ta
from .. import detection as detect

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

class Strategy:
    """Strategy base class - build new strategies on this one i think.
     idea is that each strategy handles it's signal generation and management
     we'll rename to Sigs for time being
     - process() - handle indicator updates and check our signals
     - prediction() - generate a prediction object for trade - 
     """
    def __init__(self, name):
        self.name = name
        self.signals = []

    def backfill(self,market,resolution,lookback=15):
        prices = market.prices[resolution]
        price_len = len(prices)
        if price_len - lookback > 50:

            for i in list(range(lookback,0,-1)):
                p = price_len - i
                ps = prices[:p]
                self.slow_signals(market,ps,resolution)


    def slow_signals(self,market,prices,resolution):
        """Slow signals should be used for entry when the recent movement is clear"""

        self.fast_signals(market,prices,resolution)
        
        for s in [x for x in self.signals if x.market == market.epic]:
            if not s.process():
                print("{} timed out".format(s.name))
                self.signals.remove(s)

    def fast_signals(self,market,prices,resolution):
        """Fast signals are used for closing positions"""
        ta.net_change(prices)

    def prediction(self, signal,market,resolution):
        """default stoploss and limit calculator based on atr_5"""
        prices = market.prices[resolution]
        atr, tr = ta.atr(5,prices)
        low_range = min(tr)
        max_range = max(tr)
        
        stop = atr[-1] * 2
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
            "limit_distance" : -1,
            "signal" : {
                "timestamp":signal.timestamp,
                "name" : signal.name,
                "position" : signal.position,
                "comment" : signal.comment
            }
            
        }

        return prediction_object

    def entry(self, signal, market,prices):
        """returns a true or false to whether we should open the position now"""
        pass

    def add_signal(self,signal, market):
        """makes sure that only one of each type of signal is stored"""
        matching_signals = [x for x in self.signals if x.name==signal.name and x.market==market.epic]
        for s in matching_signals:
            self.signals.remove(s)
        
        print("removed {} matching {} signals".format(len(matching_signals),signal.name))
        signal.set_market(market.epic)
        self.signals.append(signal)

    


class Sig:
    """A generic class for storing signals
    -------
    name: of signal
    position (str): BUY or SELL
    score (int): 1 instructional, 2 - can close position, 4 - can open position 
    life = how many intervals it's valid for
    """

    def __init__(self, name, timestamp, position, score, comment="", life=1):
        self.name = name
        self.timestamp = timestamp
        self.position = position
        self.score = score
        self.life = life
        self.comment = comment
        self.unused = True
        self.market = ""
        
    
    def set_market(self,market):
        self.market = market
        logger.info("new sig! : {} : {}".format(self.market, self.name))

    def process(self):
        self.life-=1
        if self.life<0:
            return False

        return True
