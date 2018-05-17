import logging
import time as systime
import os,sys
import datetime
import requests
import json
import copy
import operator
from enum import IntEnum
import numpy as np
from pytz import timezone
# from sklearn.linear_model import LinearRegression

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

class TradeState(IntEnum):
    """A state object for a trade"""
    WAITING = 0
    PENDING = 1
    OPEN = 2
    CLOSED = 3
    FAILED = 4

class Trade:

    def __init__(self,size, market, prediction, json_data = None):
        self.size_value = size
        self.market = market
        self.prediction = prediction.copy()

        self.trailing_level = 0
        self.open_level = 0

        if json_data is None:
            self.status_log = []
            
            # this trade position will expire after 10 minutes if we've failed to open it
            self.created_time = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
            mins = 60
            if "SLOW" in self.prediction['signal']['name']:
                mins = 240
            self.expiry_time = self.created_time + datetime.timedelta(minutes = mins)
            self.opened_time = None
            self.closed_time = None
            
            
            self.deal_id = "PENDING"

            
            self.profit_loss = 0
            self.pip_diff = 0
            self.pip_max = 0
            self.pip_min = 0
            self.trailing_level = 0
            self.trailing_stop = False
            
            self.stop_distance = self.market.minium_stoploss()
            if self.stop_distance < self.prediction['stoploss']:
                self.stop_distance = float(self.prediction['stoploss'])+5
            
            
            self.state = TradeState.WAITING
            
            self.log_status("Created Trade")
            self.json_obj = {}

        else:
            
            self.update_from_json(json_data)
            logger.info("Loaded trade from file {} {}".format(self.market.epic,self.deal_id))
    
        self.loop_counter = 0

    def log_status(self, message):
        """Add a message to the status list"""
        time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
        logger.info("{}: {}: '{}'".format(self.market.epic, time_now.strftime("%Y:%m:%d-%H:%M:%S"),message))
        self.status_log.append({"timestamp":time_now.strftime("%Y:%m:%d-%H:%M:%S"), "message":message})
        self.save_trade()
    


    def update(self):
        try:
            time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)


            if self.state == TradeState.CLOSED or self.state == TradeState.FAILED:
                # IF FAILED OR CLOSED, SAVE AND RETURN FALSE TO REMOVE FROM LIST
                self.log_status("Trade {}".format(TradeState(self.state).name))
                self.save_trade()
                return False

            elif self.state == TradeState.WAITING:
                if time_now > self.expiry_time:
                    self.log_status("Conditions were never right for trade to open")
                    self.state = TradeState.FAILED
                else:
                    # if self.market.ig.strategy[self.prediction['strategy']].entry(self.prediction['signal'],self.market.prices['MINUTE_30']):
                    #     self.open_trade()
                    # if self.market.strategy.entry(self.prediction['signal'],self.market.prices['MINUTE_30']):
                    self.open_trade()

            elif self.state == TradeState.PENDING:
                if time_now > self.expiry_time:
                    self.log_status("Error occured while waiting for this trade to be accepted")
                    self.state = TradeState.FAILED

            elif self.state == TradeState.OPEN:
                timeopen = time_now - self.opened_time
                # store the last full minute
                
                # calculate pip diff based on trade direction
                if self.prediction['direction_to_trade'] == "SELL":
                    self.pip_diff = float(self.open_level) - float(self.market.offer)

                else:
                    self.pip_diff = float(self.market.bid) - float(self.open_level)
                


                
                self.profit_loss = self.size_value * self.pip_diff

                # trade_logger.info("{}:{}".format(self.market.epic,self.profit_loss))
                if self.pip_diff > self.pip_max:
                    self.pip_max = self.pip_diff

                if self.pip_diff < self.pip_min:
                    self.pip_min = self.pip_diff

                # rough trail calc - update with strategy method one day?
                stoploss = float(self.prediction['stoploss'])
                self.trailing_level = stoploss - self.pip_max

                # if self.trailing_stop:

                # if self.pip_diff < -self.trailing_level:
                #     self.log_status("Trailing stop loss hit, closing at: {}".format(self.profit_loss))
                #     self.close_trade()


                # STOP LOSS CHECKING
                if float(self.pip_diff) < -stoploss and timeopen.seconds>120:
                    # price diff has dropped below artifical stop loss! ABORT!
                    self.log_status("TRADE HIT ARTIFICIAL STOPLOSS - ABORTING!")
                    self.close_trade()

            
            self.loop_counter+=1
            if self.loop_counter>10:
                if self.state == TradeState.OPEN:
                    base_url = self.market.ig.api_url + '/positions/'+ self.deal_id
                    auth_r = requests.get(base_url, headers=self.market.ig.authenticate())
                    if int(auth_r.status_code) == 400 or int(auth_r.status_code) == 404:
                        self.log_status("Can't find trade - closed in IG?")
                        self.state = TradeState.CLOSED

                self.loop_counter=0
                self.save_trade()
            
            
            return True
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info(exc_type, fname, exc_tb.tb_lineno)
            pass


    def open_trade(self):
        time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
        self.state = TradeState.PENDING
        self.expiry_time = time_now + datetime.timedelta(minutes = 5)
        self.log_status("Attempting to open trade")
        limit = 150
        if float(self.prediction['limit_distance']) > 0:
            limit = float(self.prediction['limit_distance'])
        base_url = self.market.ig.api_url + '/positions/otc'
        # logger.info("prediction: {}".format(self.prediction))
        data = {
            "direction":self.prediction["direction_to_trade"],
            "epic": self.market.epic, 
            "limitDistance":limit, 
            "orderType":"MARKET", 
            "size":self.size_value,
            "expiry":"DFB",
            "guaranteedStop":True,
            "currencyCode":"GBP",
            "forceOpen":True,
            "stopDistance":self.stop_distance
        }
        res = requests.post(base_url, data=json.dumps(data), headers=self.market.ig.authenticate())

        if res.ok:
            
            d = json.loads(res.text)
            deal_ref = d['dealReference']
            systime.sleep(2)

            base_url = self.market.ig.api_url + '/confirms/'+ deal_ref
            auth_r = requests.get(base_url, headers=self.market.ig.authenticate())
            if auth_r.ok:
                
                d = json.loads(auth_r.text)
                self.deal_id = d['dealId']
                logger.info("DEAL ID : " + str(d['dealId']))
                logger.info(d['dealStatus'])
                logger.info(d['reason'])
                if d['dealStatus'] == "ACCEPTED":
                    
                    self.opened_time = time_now
                    self.log_status("Trade Accepted")
                    systime.sleep(2)
                    # read in data to get the deal cost etc
                    base_url = self.market.ig.api_url + '/positions/'+ self.deal_id
                    auth_r = requests.get(base_url, headers=self.market.ig.authenticate())

                    if auth_r.ok:
                        d = json.loads(auth_r.text)
                        logger.info(d)
                        self.open_level = d['position']['openLevel']

                        # trade successfully created - save the object YAYAYAYAAYYYYY
                        self.state = TradeState.OPEN
                        self.save_trade()
                    else:
                        self.log_status("Shit - couldn't read in deal - need retry somehow")
                else:
                    # something wrong with the attempted trade, cooldown this market
                    logger.info(self.market.epic)
                    self.log_status("Trade rejected: {}".format(d['reason']))
                    if d['reason']=="ATTACHED_ORDER_LEVEL_ERROR":
                        # bump the stop order a bit?
                        if self.stop_distance+5<250:
                            self.stop_distance = min(self.stop_distance+5,255)
                            self.log_status("Bumping stop distance to {}".format(self.stop_distance))
                            self.state =TradeState.WAITING
                        else:
                            self.state = TradeState.FAILED
                            self.market.cooldown = time_now + datetime.timedelta(minutes = 30)

                    else:
                        self.state = TradeState.FAILED
                        self.market.cooldown = time_now + datetime.timedelta(minutes = 30)

                    self.save_trade()

            else:
                # sending the trade wasn't successful
                logger.info(self.market.epic)
                self.log_status("Trade request failed")
                self.log_status(res.content)
                self.state = TradeState.FAILED
                self.market.cooldown = time_now + datetime.timedelta(minutes = 30)
                self.save_trade()
        
        else:
            self.log_status("Trade failed")
            self.log_status(res.content)
            self.state = TradeState.FAILED

    def close_trade(self):
        time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
        self.log_status("CLOSING TRADE")
        delete_header = self.market.ig.authenticate().copy()
        delete_header['_method'] = "DELETE"
        base_url = self.market.ig.api_url + '/positions/otc'
        data = {"dealId":self.deal_id,"direction":self.prediction['direction_to_close'],"size":self.size_value,"orderType":"MARKET"}

        auth_r = requests.post(base_url, data=json.dumps(data), headers=delete_header) 

        if auth_r.ok:
            self.closed_time = time_now
            logger.info(auth_r.status_code)
            logger.info(auth_r.reason)
            logger.info (auth_r.text)
            self.state = TradeState.CLOSED
            self.save_trade()
        else:
            logger.info("SHIT THE BED SOMETHING WENT WRONG WITH CLOSING THE TRADE - PANIC")
            logger.info(auth_r.status_code)
            logger.info(auth_r.reason)
            logger.info(auth_r.text)
            # something retarded has happened, but we can't find the deal so consider it closed
            if "No position found for AccountId" in auth_r.text:
                self.closed_time = time_now
                self.state = TradeState.CLOSED
                self.save_trade()
            

    def assess_close(self,signal):
        """checks to see whether it's a good idea to use the given signal to close the deal"""
        # self.log_status("CLOSED BY SIGNAL: {}".format(signal))
        self.close_trade()
        # return
        # time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
        # if self.opened_time is not None:
        #     timeopen = time_now - self.opened_time
        #     #for now, just close the trade regardless
        #     self.close_trade()
        #     if timeopen.seconds/60 < 120:
        #         self.log_status("SHIT MARKET'S CHANGED MIND!?")
        #         self.close_trade()

        #     if self.pip_diff<0.2:
        #         self.log_status("{} opposing signal {} found - but not in profit. max{}".format(self.market.epic,signal.position, self.pip_max))
        #         return
        #     # if self.pip_diff < self.prediction['limit_distance']:
        #     #     return

        #     self.log_status("{} opposing signal {} found - activate trailing stoploss. Old max {}".format(self.market.epic,signal.position, self.pip_max))
        #     self.pip_max = self.pip_diff
            # self.trailing_stop = True
    

    def update_from_json(self, json_data):
        try:
            close_t = datetime.datetime.strptime(json_data['closed_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=None)
        except Exception as e:
            close_t = None
        try:
            open_t = datetime.datetime.strptime(json_data['opened_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=None)
        except Exception as e:
            open_t = None

        

        self.size_value = json_data['size_value']
        self.prediction = json_data['prediction']
        self.deal_id = json_data['deal_id']
        self.state = json_data['state']
        self.created_time = datetime.datetime.strptime(json_data['created_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=None)
        self.expiry_time = datetime.datetime.strptime(json_data['expiry_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=None)

        

        self.opened_time = open_t
        self.closed_time = close_t


        self.open_level = float(json_data['open_level'])
        self.pip_diff = float(json_data['pip_diff'])
        self.pip_max = json_data['pip_max']
        self.pip_min = getattr(json_data,'pip_min',0)

        self.profit_loss = float(json_data['profit_loss'])
        self.trailing_stop = json_data['trailing_stop']

        self.status_log = json_data['status_log']

    def save_trade(self):

        try:
            close_t = self.closed_time.strftime("%Y:%m:%d-%H:%M:%S")
        except Exception as e:
            close_t = None
        try:
            open_t = self.opened_time.strftime("%Y:%m:%d-%H:%M:%S")
        except Exception as e:
            open_t = None
        try:
            save_object = {
                "last_saved" : datetime.datetime.now(timezone('GB')).replace(tzinfo=None).strftime("%Y:%m:%d-%H:%M:%S"),
                "size_value" : self.size_value,
                "prediction" : self.prediction,
                "deal_id" : self.deal_id,
                "market" : self.market.epic,
                "state" : self.state,
                "created_time" : self.created_time.strftime("%Y:%m:%d-%H:%M:%S"),
                "expiry_time" : self.expiry_time.strftime("%Y:%m:%d-%H:%M:%S"),
                "opened_time" : open_t,
                "closed_time" : close_t,
                "open_level" : self.open_level,
                "pip_diff" : round(self.pip_diff,2),
                "pip_min" : round(self.pip_min,2),
                "pip_max" : round(self.pip_max,2),
                "profit_loss" : round(self.profit_loss,2),
                "trailing_level":round(self.trailing_level,2),
                "trailing_stop":self.trailing_stop,
                "status_log" : self.status_log
            }
            filename = self.created_time.strftime("%Y-%m-%d-%H-%M-%S") + "---" + self.market.epic + ".json"
            filepath = "trades/open/" 
            
            if self.state == TradeState.CLOSED or self.state == TradeState.FAILED:
                # delete the old open file
                try:
                    os.remove(filepath + filename)
                except OSError:
                    pass
                filepath = "trades/closed/"
                if self.state == TradeState.FAILED:
                    filepath = "trades/failed/"

            if not os.path.exists(filepath):
                os.makedirs(filepath)

            fh = open(filepath + filename,"w")
            json.dump(save_object,fh)
            fh.close()

            self.json_obj = save_object
        except Exception as e:
            logger.info("Couldn't save trade for some reason")
            logger.info(e)
