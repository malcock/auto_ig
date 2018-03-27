import logging
import os
import datetime
import json
import requests
import numpy as np
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

class Signal:
    
    def __init__(self, epic, resolution, snapshotTime, action, signalType, comment = "", confirmed = False):
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
        
        self.confirmed = confirmed

        self.active = True
        self.unused = True
        self.comment = comment

        self.score = 1 #need to think of how to properly grade different signals - probably upon being confirmed?
        timeout_multiplier = 1
        if self.type == "RVI":
            timeout_multiplier = 25
            self.score = 1
        elif self.type == "MA":
            self.score = 2
        elif self.type == "MACD":
            self.score = 2
            if self.confirmed:
                self.score = 4
        elif self.type == "RSI":
            timeout_multiplier = 4
            self.score = 1
        elif self.type == "STOCH":
            timeout_multiplier = 4
            self.score = 1
        elif self.type == "PSAR":
            timeout_multiplier = 2
            self.score = 2
            if self.confirmed:
                self.score = 4

        # work out the exiry time for this signal - depending on type, plus 2mins
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
        seconds_per_unit = (seconds_per_unit * timeout_multiplier) + 1200

        self.expiry_time = datetime.datetime.strptime(self.snapshot_time,"%Y:%m:%d-%H:%M:%S").replace(tzinfo=None) + datetime.timedelta(seconds = seconds_per_unit)
        
        logger.info("NEW SIGNAL! {} {} {} {}".format(self.epic,self.snapshot_time,self.type,self.action))

    def update(self, market):
        time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
        if time_now > self.expiry_time:
            logger.info("SIGNAL EXPIRED {} {} {} {}".format(self.epic,self.snapshot_time,self.type,self.action))
            return False
        # prices = market.prices[self.resolution]
        # i = next((index for (index, d) in enumerate(prices) if d["snapshotTime"] == self.snapshot_time), None)
        
        # total = sum([abs(x['macd_histogram']) for x in market.prices[self.resolution][i:]])
        # self.score = 2 + total
        # # only check until it's been confirmed to conserve cpu usage
        # if not self.confirmed:
            
        #     if i<len(prices)-1:
        #         last_price = prices[-1]['macd_histogram']
        #         # logger.info("{} {} {} confirm:{} current:{}".format(self.epic,self.snapshot_time,self.action, self.confirmation_price,last_price))
        #         if self.action=="BUY":
        #             if last_price > self.confirmation_price:
        #                 self.confirmed = True
        #         else:
        #             if last_price < self.confirmation_price:
        #                 self.confirmed = True

            
        #     if self.confirmed:
        #         logger.info("SIGNAL CONFIRMED {} {} {} {}".format(self.epic,self.snapshot_time,self.type,self.action))
                
        #         self.active = False
        #         # do something to rescore this based on something - like multiple signals being confirmed at once?
        # else:
        #     total = sum([abs(x['macd_histogram']) for x in market.prices[self.resolution][i:]])
        #     self.score = 2 + total


        return True
