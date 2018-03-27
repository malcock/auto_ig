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
        self.overtime = False
        self.pip_rate = 0
        self.bad_intervals = 0 #if this reaches x, close the trade
        self.best_minute = None
        self.trailing_level = 0
        self.open_level = 0

        if json_data is None:
            self.status_log = []
            
            # this trade position will expire after 10 minutes if we've failed to open it
            self.created_time = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
            self.expiry_time = self.created_time + datetime.timedelta(minutes = 180)
            self.opened_time = None
            self.closed_time = None
            
            self.rsi_max = 0
            self.rsi_min = 100
            self.rsi_init = self.market.current_rsi
            self.deal_id = "PENDING"

            
            self.profit_loss = 0
            self.pip_diff = 0
            self.pip_max = 0
            self.trailing_level = 0
            self.trailing_stop = False
            self.stop_distance = 150
            
            
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
    
    def update_interval(self, resolution):
        """Run every *resolution* to check on what's going on to check for trades that are going south"""
        last_interval = self.market.prices[resolution][-2]
        prev_interval = self.market.prices[resolution][-3]

        self.rsi_max = max(self.rsi_max,prev_interval['rsi'])
        self.rsi_min = min(self.rsi_min,prev_interval['rsi'])

        if self.pip_diff < 0:
            # negative, monitor for declining conditions

            if self.prediction['direction_to_trade'] == "SELL":
                price_diff = prev_interval['ema_12'] - last_interval['ema_12']
                
            else:
                price_diff = last_interval['ema_12'] - prev_interval['ema_12']
                

            if price_diff>0:
                return
            
            # check if the price has dropped, despite market momentum against it
            if self.prediction['direction_to_trade'] == "BUY" and last_interval['macd_histogram'] > 0:
                self.bad_intervals+=1
                self.log_status("price falling despite positive pressure at {}".format(last_interval['snapshotTime']))

            if self.prediction['direction_to_trade'] == "SELL" and last_interval['macd_histogram'] < 0:
                self.bad_intervals+=1
                self.log_status("price rising despite negative pressure at {}".format(last_interval['snapshotTime']))

            
                
            # check against macd histo
            
        else:
            # positive - monitor for maxed RSI exit points
            pass


        


        

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
                    self.log_status("Error occured while waiting for this trade to be accepted")
                    self.state = TradeState.FAILED
                
                if self.prediction['direction_to_trade'] == "BUY":
                    if self.market.prices['MINUTE_30'][-1]['momentum']>1:
                        self.open_trade()
                else:
                    if self.market.prices['MINUTE_30'][-1]['momentum']>1:
                        self.open_trade()
                # self.open_trade()

            elif self.state == TradeState.PENDING:
                if time_now > self.expiry_time:
                    self.log_status("Error occured while waiting for this trade to be accepted")
                    self.state = TradeState.FAILED

            elif self.state == TradeState.OPEN:
                timeopen = time_now - self.opened_time
                # store the last full minute
                last_minute =  self.market.prices['MINUTE_30'][-2]
                if self.best_minute is None:
                    self.best_minute = last_minute.copy()

                trail = 0
                # calculate pip diff based on trade direction and check our best minute
                if self.prediction['direction_to_trade'] == "SELL":
                    self.pip_diff = float(self.open_level) - float(self.market.offer)
                    last_bear = [x['psar_bear'] for x in self.market.prices['MINUTE_30'] if x['psar_bear']!=''][-1]
                    trail = float(self.open_level) - last_bear

                    if last_minute['closePrice']['ask'] < self.best_minute['closePrice']['ask']:
                        if last_minute['rsi'] > self.best_minute['rsi'] and self.trailing_stop==False:
                            # self.log_status("Lower price without lower RSI - triggering trailing stop at {} ".format(self.pip_diff))
                            # self.trailing_stop = True
                            pass
                        else:
                            self.best_minute = last_minute.copy()
                        
                else:
                    self.pip_diff = float(self.market.bid) - float(self.open_level)
                    last_bull = [x['psar_bull'] for x in self.market.prices['MINUTE_30'] if x['psar_bull']!=''][-1]
                    trail = last_bull - float(self.open_level)

                    if last_minute['closePrice']['bid'] > self.best_minute['closePrice']['bid'] and self.trailing_stop==False:
                        if last_minute['rsi'] < self.best_minute['rsi']:
                            # self.log_status("Higher price without higher RSI - triggering trailing stop at {}".format(self.pip_diff))
                            # self.trailing_stop = True
                            pass
                        else:
                            self.best_minute = last_minute.copy()

                

                self.pip_rate = self.pip_diff / (timeopen.seconds/60)

                if self.pip_rate < -1 and timeopen.seconds/60 > 5:
                    self.log_status("SHIT PIPS FALLING LIKE KNIVES")

                self.rsi_max = max(self.rsi_max,self.market.current_rsi)
                self.rsi_min = min(self.rsi_min,self.market.current_rsi)
                
                self.profit_loss = self.size_value * self.pip_diff

                # trade_logger.info("{}:{}".format(self.market.epic,self.profit_loss))
                if self.pip_diff > self.pip_max:
                    self.pip_max = self.pip_diff

                self.trailing_level = max(self.pip_max-5,trail)
                self.trailing_level = max(1.1,trail)

                if self.trailing_stop:

                    
                    if 0 < self.pip_diff < self.trailing_level:
                        self.log_status("Trailing stop loss hit, closing at: {}".format(self.profit_loss))
                        self.close_trade()
                

                # STOP LOSS CHECKING
                stoploss = float(self.prediction['stoploss'])

                # HOPEFUL TIMEOUT CHECKING - TODO: Create an acceptable profit loss shaping curve
                
                # logger.info(timeopen.seconds)
                # if timeopen.seconds/60>120:
                #     if not self.overtime and self.pip_diff < 0:
                #         self.overtime = True
                #         self.trailing_stop = True
                #         self.log_status("ORDER OPEN 2 HOURS OVERTIME - TAKING NEXT PROFIT")
                

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

        base_url = self.market.ig.api_url + '/positions/otc'
        # logger.info("prediction: {}".format(self.prediction))
        data = {
            "direction":self.prediction["direction_to_trade"],
            "epic": self.market.epic, 
            "limitDistance":150, 
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
                        if self.stop_distance+10<175:
                            self.stop_distance = min(self.stop_distance+5,175)
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
        time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
        if self.opened_time is not None:
            timeopen = time_now - self.opened_time
            #for now, just close the trade regardless
            self.close_trade()
            if timeopen.seconds/60 < 120:
                self.log_status("SHIT MARKET'S CHANGED MIND!?")
                self.close_trade()

            if self.pip_diff<0.2:
                self.log_status("{} opposing signal {} found - but not in profit. max{}".format(self.market.epic,signal.action, self.pip_max))
                return
            # if self.pip_diff < self.prediction['limit_distance']:
            #     return

            self.log_status("{} opposing signal {} found - activate trailing stoploss. Old max {}".format(self.market.epic,signal.action, self.pip_max))
            self.pip_max = self.pip_diff
            self.trailing_stop = True
    

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

        # some temp error fixing
        if open_t is None:
            open_t = self.created_time

        self.opened_time = open_t
        self.closed_time = close_t
        self.bad_intervals = json_data.get('bad_intervals',0)
        self.pip_rate = json_data.get('pip_rate',0)
        

        self.best_minute = json_data.get('best_minute',None)

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
                "rsi_init" : self.rsi_init,
                "rsi_max" : self.rsi_max,
                "rsi_min" : self.rsi_min,
                "bad_intervals" : self.bad_intervals,
                "best_minute":self.best_minute,
                "pip_rate": self.pip_rate,
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
