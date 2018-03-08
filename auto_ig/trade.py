import logging
import time as systime
import os
import datetime
import requests
import json
import copy
import operator
from enum import IntEnum
import numpy as np
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

        if json_data is None:
            self.status_log = []
            
            # this trade position will expire after 10 minutes if we've failed to open it
            self.created_time = datetime.datetime.now(datetime.timezone.utc)
            self.expiry_time = self.created_time + datetime.timedelta(minutes = 10)
            self.opened_time = None
            self.closed_time = None
            
            self.rsi_max = 0
            self.rsi_min = 100
            self.rsi_init = self.market.current_rsi
            self.deal_id = "PENDING"

            self.open_level = 0
            self.profit_loss = 0
            self.pip_diff = 0
            self.pip_max = 0
            self.trailing_level = 0
            self.trailing_stop = False
            self.stop_distance = 150
            
            self.state = TradeState.WAITING
            self.overtime = False
            self.log_status("Created Trade")
            self.json_obj = {}

        else:
            
            self.update_from_json(json_data)
            logger.info("Loaded trade from file {} {}".format(self.market.epic,self.deal_id))
    
        self.loop_counter = 0

    def log_status(self, message):
        """Add a message to the status list"""
        logger.info("{}: {}: '{}'".format(self.market.epic, datetime.datetime.now(datetime.timezone.utc).strftime("%Y:%m:%d-%H:%M:%S"),message))
        self.status_log.append({"timestamp":datetime.datetime.now(datetime.timezone.utc).strftime("%Y:%m:%d-%H:%M:%S"), "message":message})
        self.save_trade()

    def update(self):
        
        if self.state == TradeState.CLOSED or self.state == TradeState.FAILED:
            # IF FAILED OR CLOSED, SAVE AND RETURN FALSE TO REMOVE FROM LIST
            self.log_status("Trade {}".format(TradeState(self.state).name))
            self.save_trade()
            return False

        elif self.state == TradeState.WAITING:
            if datetime.datetime.now(datetime.timezone.utc) > self.expiry_time:
                self.log_status("Error occured while waiting for this trade to be accepted")
                self.state = TradeState.FAILED

            self.open_trade()

        elif self.state == TradeState.PENDING:
            if datetime.datetime.now(datetime.timezone.utc) > self.expiry_time:
                self.log_status("Error occured while waiting for this trade to be accepted")
                self.state = TradeState.FAILED

        elif self.state == TradeState.OPEN:
            
            if self.prediction['direction_to_trade'] == "SELL":
                self.pip_diff = float(self.open_level) - float(self.market.offer)
            else:
                self.pip_diff = float(self.market.bid) - float(self.open_level)

            self.rsi_max = max(self.rsi_max,self.market.current_rsi)
            self.rsi_min = min(self.rsi_min,self.market.current_rsi)
            
            self.profit_loss = self.size_value * self.pip_diff

            # trade_logger.info("{}:{}".format(self.market.epic,self.profit_loss))
            if self.pip_diff > self.pip_max:
                self.pip_max = self.pip_diff

            
            self.trailing_level = max(1.1,self.pip_max-4)

            if float(self.pip_diff) > float(self.prediction['limit_distance']) and self.trailing_stop==False:
                self.trailing_stop = True
                self.log_status("Trailing stop threshold passed at {}".format(self.profit_loss))
                
            if self.trailing_stop:
                if self.pip_diff<self.trailing_level:
                    self.log_status("Trailing stop loss hit, closing at: {}".format(self.profit_loss))
                    self.close_trade()


            # STOP LOSS CHECKING
            stoploss = float(self.prediction['stoploss'])

            # HOPEFUL TIMEOUT CHECKING - TODO: Create an acceptable profit loss shaping curve
            timeopen = datetime.datetime.now(datetime.timezone.utc) - self.opened_time
            # logger.info(timeopen.seconds)
            if timeopen.seconds/60>120:
                if not self.overtime:
                    self.overtime = True
                    self.prediction['limit_distance'] = float(self.prediction['atr_low'])/2
                    self.log_status("ORDER OPEN 2 HOURS OVERTIME - HALVING LIMIT")
            

            if float(self.pip_diff) < -stoploss:
                # price diff has dropped below artifical stop loss! ABORT!
                self.log_status("TRADE HIT ARTIFICIAL STOPLOSS - ABORTING!")
                self.close_trade()

            self.loop_counter+=1
            if self.loop_counter>10:
                if self.state == TradeState.OPEN:
                    base_url = self.market.ig.api_url + '/positions/'+ self.deal_id
                    auth_r = requests.get(base_url, headers=self.market.ig.authenticate())
                    if int(auth_r.status_code) == 400 or int(auth_r.status_code) == 404:
                        self.status_log("Can't find trade - closed in IG?")
                        self.state = TradeState.CLOSED

                self.loop_counter=0
                self.save_trade()
        
        return True


    def open_trade(self):

        self.state = TradeState.PENDING
        self.expiry_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes = 5)
        self.log_status("Attempting to open trade")

        base_url = self.market.ig.api_url + '/positions/otc'
        # logger.info("prediction: {}".format(self.prediction))
        data = {
            "direction":self.prediction["direction_to_trade"],
            "epic": self.market.epic, 
            "limitDistance":100, 
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
                    
                    self.opened_time = datetime.datetime.now(datetime.timezone.utc)
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
                        if self.stop_distance+10<175:
                            self.stop_distance = min(self.stop_distance+5,175)
                            self.log_status("Bumping stop distance to {}".format(self.stop_distance))
                            self.state =TradeState.WAITING
                        else:
                            self.state = TradeState.FAILED
                            self.market.cooldown = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes = 10)

                    else:
                        self.state = TradeState.FAILED
                        self.market.cooldown = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes = 10)

                    self.save_trade()

            else:
                # sending the trade wasn't successful
                logger.info(self.market.epic)
                self.log_status("Trade request failed")
                self.log_status(res.content)
                self.state = TradeState.FAILED
                self.market.cooldown = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes = 10)
                self.save_trade()
        
        else:
            self.log_status("Trade failed")
            self.log_status(res.content)
            self.state = TradeState.FAILED

    def close_trade(self):
        self.log_status("CLOSING TRADE")
        delete_header = self.market.ig.authenticate().copy()
        delete_header['_method'] = "DELETE"
        base_url = self.market.ig.api_url + '/positions/otc'
        data = {"dealId":self.deal_id,"direction":self.prediction['direction_to_close'],"size":self.size_value,"orderType":"MARKET"}

        auth_r = requests.post(base_url, data=json.dumps(data), headers=delete_header) 

        if auth_r.ok:
            self.closed_time = datetime.datetime.now(datetime.timezone.utc)
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

    def assess_close(self,signal):
        """checks to see whether it's a good idea to use the given signal to close the deal"""
        if self.pip_diff<0.2:
            return
        if self.pip_diff < self.prediction['limit_distance']:
            return
        self.close_trade()            

    def update_from_json(self, json_data):
        try:
            close_t = datetime.datetime.strptime(json_data['closed_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except Exception as e:
            close_t = None
        try:
            open_t = datetime.datetime.strptime(json_data['opened_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except Exception as e:
            open_t = None

        

        self.size_value = json_data['size_value']
        self.prediction = json_data['prediction']
        self.deal_id = json_data['deal_id']
        self.state = json_data['state']
        self.created_time = datetime.datetime.strptime(json_data['created_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        self.expiry_time = datetime.datetime.strptime(json_data['expiry_time'],"%Y:%m:%d-%H:%M:%S").replace(tzinfo=datetime.timezone.utc)

        # some temp error fixing
        if open_t is None:
            open_t = self.created_time

        self.opened_time = open_t
        self.closed_time = close_t
        
        self.rsi_init = json_data['rsi_init']
        self.rsi_max = json_data['rsi_max']
        self.rsi_min = json_data['rsi_min']
        self.open_level = float(json_data['open_level'])
        self.pip_diff = float(json_data['pip_diff'])
        self.pip_max = json_data['pip_max']

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
                "last_saved" : datetime.datetime.now(datetime.timezone.utc).strftime("%Y:%m:%d-%H:%M:%S"),
                "size_value" : self.size_value,
                "prediction" : self.prediction,
                "deal_id" : self.deal_id,
                "market" : self.market.epic,
                "state" : self.state,
                "created_time" : self.created_time.strftime("%Y:%m:%d-%H:%M:%S"),
                "expiry_time" : self.expiry_time.strftime("%Y:%m:%d-%H:%M:%S"),
                "opened_time" : open_t,
                "closed_time" : close_t,
                "rsi_init" : self.rsi_init,
                "rsi_max" : self.rsi_max,
                "rsi_min" : self.rsi_min,
                "open_level" : self.open_level,
                "pip_diff" : round(self.pip_diff,2),
                "pip_max" : self.pip_max,
                "profit_loss" : round(self.profit_loss,2),
                "trailing_level":self.trailing_level,
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
