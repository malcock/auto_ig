# from ..sig import Sig
from .. import indicators as ta
from .. import detection as detect
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

    def backfill(self,prices,lookback=15):
        price_len = len(prices)
        if price_len - lookback > 50:

            for i in list(range(lookback,0,-1)):
                p = price_len - i
                ps = prices[:p]
                self.process(ps)

        print(self.signals)

    def process(self,prices):
        ta.direction(prices)
        for s in self.signals:
            if not s.process():
                print("{} timed out".format(s.name))
                self.signals.remove(s)

    def prediction(self, signal, prices):
        """default stoploss and limit calculator based on atr_5"""
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

    def entry(self, signal, prices):
        """returns a true or false to whether we should open the position now"""
        pass

    def add_signal(self,signal):
        """makes sure that only one of each type of signal is stored"""
        matching_signals = [x for x in self.signals if x.name==signal.name]
        for s in matching_signals:
            self.signals.remove(s)
        
        print("removed {} matching {} signals".format(len(matching_signals),signal.name))

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
        print("new sig! : {}".format(self.name))

    def process(self):
        self.life-=1
        if self.life<0:
            return False

        return True
