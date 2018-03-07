import logging
import os
import datetime
import json
import requests
import numpy as np

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

class Signal:
    
    def __init__(self, epic, resolution, snapshotTime, action, signalType, confirmation_price = None):
        """Create a signal object stores it's state to confirm buy or sell signals
            resolution = what res was this signal discovered at?
            snapshot = when this signal was generated on the price list
            Action = "BUY | SELL"
            SignalType = "HAMMER | RSI PEAK | RSI NADIR" etc
            confirmation = what price does the next unit need to close at to confirm this signal?
        """
        self.epic = epic
        self.resolution = resolution
        self.snapshot_time = snapshotTime
        
        self.action = action
        self.type = signalType
        self.confirmation_price = 0
        if confirmation_price is not None:
            self.confirmation_price = confirmation_price
            self.confirmed = False
        else:
            self.confirmed = True

        self.active = True
        self.unused = True

        self.score = 1 #need to think of how to properly grade different signals - probably upon being confirmed?

        if self.type == "HAMMER":
            self.score = 0.75
        elif self.type == "CROSSOVER":
            self.score = 1

        # work out the exiry time for this signal - 4 times resolution, plus 2mins
        seconds_per_unit = 0
        if "MINUTE" in resolution:
            seconds_per_unit = 60
        elif "HOUR" in resolution:
            seconds_per_unit = 60 * 60
        else:
            seconds_per_unit = 60 * 60 * 24
        
        if "_" in resolution:
            multiplier = int(resolution.split("_")[1])
            seconds_per_unit *= multiplier
        seconds_per_unit = (seconds_per_unit * 4) + 120

        self.expiry_time = datetime.datetime.strptime(self.snapshot_time,"%Y:%m:%d-%H:%M:%S") + datetime.timedelta(seconds = seconds_per_unit)
        self.expiry_time = self.expiry_time.replace(tzinfo=datetime.timezone.utc)
        
        logger.info("NEW SIGNAL! {} {} {} {}".format(self.epic,self.snapshot_time,self.type,self.action))

    def update(self, market):
        if datetime.datetime.now(datetime.timezone.utc) > self.expiry_time:
            logger.info("SIGNAL EXPIRED {} {} {} {}".format(self.epic,self.snapshot_time,self.type,self.action))
            return False
        
        # only check until it's been confirmed to cpu usage
        if self.active:
            prices = market.prices[self.resolution]
            i = next((index for (index, d) in enumerate(prices) if d["snapshotTime"] == self.snapshot_time), None)
            if i<len(prices)-1:
                last_price = prices[-1]['closePrice']['bid']
                # logger.info("{} {} {} confirm:{} current:{}".format(self.epic,self.snapshot_time,self.action, self.confirmation_price,last_price))
                if self.action=="BUY":
                    if last_price > self.confirmation_price:
                        self.confirmed = True
                        self.active = False
                else:
                    if last_price < self.confirmation_price:
                        self.confirmed = True
                        self.active = False

            
            if self.confirmed:
                logger.info("SIGNAL CONFIRMED {} {} {} {}".format(self.epic,self.snapshot_time,self.type,self.action))
                # do something to rescore this based on something - like multiple signals being confirmed at once?

     
        return True