import logging
import os, sys
import datetime
import json
import math
import operator
import requests
import numpy as np
from pytz import timezone

from .signal import Signal
from . import indicators as ta
from .strategy import wma_cross

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


class Market:
    """Main class for handling monitoring of markets and producing signals"""
    
    def __init__(self, epic, ig_obj, market_data = None):
        self.epic = epic
        self.cooldown = datetime.datetime(2000,1,1,0,0,0,0)
        self.ig = ig_obj
        # raw data and signal producers
        self.prices = {}
        self.strategies = {}
        self.data = {}
        self.last_bigstamp = ""
        self.last_status = ""
        self.dealing_rules = {}
        self.margin_bands = {}
        self.risk_premium = {}
        self.minimum_stop = 0

        self.market_status =""
        
        self.load_prices()
        self.update_market(market_data)

    def add_strategy(self, strategy):
        if strategy.name not in self.strategies:
            self.strategies[strategy.name] = strategy

    def update_market(self, obj = None):
        if obj is None:
            logger.info("getting " + self.epic + " market data")
            base_url = self.ig.api_url + '/markets/' + self.epic
            auth_r = requests.get(base_url, headers=self.ig.authenticate())
            obj = json.loads(auth_r.text)
        
        # store the status of the market from the obj, use a change in state to trigger an update to lightstreamer in auto_ig.py
        self.market_status = obj['snapshot']['marketStatus']
        
        # maybe we can load some prices?
        self.bid = float(obj['snapshot']['bid'])
        self.offer = float(obj['snapshot']['offer'])
        self.spread = self.offer - self.bid
        self.high = float(obj['snapshot']['high'])
        self.low = float(obj['snapshot']['low'])
        self.percentage_change = float(obj['snapshot']['percentageChange'])
        self.net_change = float(obj['snapshot']['netChange'])

        self.dealing_rules = obj['dealingRules']
        self.margin_bands = obj['instrument']['marginDepositBands']
        self.risk_premium = obj['instrument']['limitedRiskPremium']
        self.minimum_stop = self.minimum_stoploss()
        
        if self.market_status=="TRADEABLE":
            if "DAY" in self.prices:
                self.prices['DAY'][-1]['highPrice']['bid'] = self.high
                self.prices['DAY'][-1]['lowPrice']['bid'] = self.low
                self.prices['DAY'][-1]['openPrice']['bid'] = self.bid - self.net_change
                self.prices['DAY'][-1]['closePrice']['bid'] = self.bid

        else:
            self.prices = {}
            self.save_prices()
            return
        
        
        self.save_json()

    def minimum_stoploss(self):
        if self.dealing_rules['minControlledRiskStopDistance']['unit']=="POINTS":
            return float(self.dealing_rules['minControlledRiskStopDistance']['value'])
        else:
            mid = ((float(self.bid) + float(self.offer))/2.0)*0.01
            return mid * float(self.dealing_rules['minControlledRiskStopDistance']['value'])
        


    def margin_required(self,bet_size):
        stop_loss = self.minimum_stoploss()
        return math.ceil((bet_size * stop_loss) + (bet_size * float(self.risk_premium['value'])))

            

    def set_latest_price(self,values):
        # if self.ready:
        try:
            timestamp = datetime.datetime.fromtimestamp(int(values['UTM'])/1000,timezone('GB')).strftime("%Y:%m:%d-%H:%M:00")
            minNum = datetime.datetime.fromtimestamp(int(values['UTM'])/1000).strftime("%M") #1 or 6? make a new MIN_5
            minNum = float(minNum)
            
            self.bid = float(values['BID_CLOSE'])
            self.offer = float(values['OFR_CLOSE'])
            self.high = float(values['DAY_HIGH'])
            self.low = float(values['DAY_LOW'])
            self.spread = float(self.offer) - float(self.bid)
            if "DAY" in self.prices:
                if len(self.prices['DAY'])>0:
                    last_day = self.prices['DAY'][-1]
                    # print(last_day)
                    # print(last_day[-1])
                    last_day['highPrice']['bid'] = self.high
                    last_day['lowPrice']['bid'] = self.low
                    last_day['openPrice']['bid'] = self.bid - self.net_change
                    last_day['closePrice']['bid'] = self.bid
                    # print(last_day)
            # create an empty price object that matches the hsitorical one
            current_price = {
                    "snapshotTime": timestamp, 
                    "openPrice": {"bid": float(values['BID_OPEN']), "ask": float(values['OFR_OPEN']), "mid": (float(values['BID_OPEN']) + float(values['OFR_OPEN']))/2, "lastTraded": None}, 
                    "closePrice": {"bid": self.bid, "ask": float(values['OFR_CLOSE']), "mid": (float(values['BID_CLOSE']) + float(values['OFR_CLOSE']))/2, "lastTraded": None }, 
                    "highPrice": {"bid": float(values['BID_HIGH']), "ask": float(values['OFR_HIGH']), "mid": (float(values['BID_HIGH']) + float(values['OFR_HIGH']))/2, "lastTraded": None}, 
                    "lowPrice": {"bid": float(values['BID_LOW']), "ask": float(values['OFR_LOW']), "mid": (float(values['BID_LOW']) + float(values['OFR_LOW']))/2, "lastTraded": None}, 
                    "lastTradedVolume": int(values['LTV'])}
            self.typical_price(current_price,"mid")
            self.price_spread(current_price)
            
            if "MINUTE_5" in self.prices:
                # use the timestamp to save the value to the right minute object in the list or make a new one
                i = next((index for (index, d) in enumerate(self.prices['MINUTE_5']) if d["snapshotTime"] == timestamp), None)
                if i==None:

                    self.prices['MINUTE_5'].append(current_price)
                    

                    if "MINUTE_30" in self.prices:
                        last_30_min = int(30 * math.floor(minNum/30))
                        timestamp_30 = datetime.datetime.fromtimestamp(int(values['UTM'])/1000,timezone('GB')).strftime("%Y:%m:%d-%H:{:0>2d}:00".format(last_30_min))
                        
                        # get all elements from MINUTE list since last 5min mark
                        i = next((index for (index, d) in enumerate(self.prices['MINUTE_5']) if d["snapshotTime"] == timestamp_30), None)
                        mins = self.prices['MINUTE_5'][i:]
                        open_price = mins[0]['openPrice']
                        close_price = mins[-1]['closePrice']
                        vol = sum([x['lastTradedVolume'] for x in mins])
                        ask_low = min([x['lowPrice']['ask'] for x in mins])
                        ask_high = max([x['highPrice']['ask'] for x in mins])
                        bid_low = min([x['lowPrice']['bid'] for x in mins])
                        bid_high = max([x['highPrice']['bid'] for x in mins])
                        new_30_min = {
                            "snapshotTime": timestamp_30, 
                            "openPrice": {"bid": float(open_price['bid']), "ask": float(open_price['ask']), "mid": (float(open_price['bid']) + float(open_price['ask']))/2, "lastTraded": None}, 
                            "closePrice": {"bid": float(close_price['bid']), "ask": float(close_price['ask']), "mid": (float(close_price['bid']) + float(close_price['ask']))/2, "lastTraded": None }, 
                            "highPrice": {"bid": float(bid_high), "ask": float(ask_high), "mid": (float(bid_high) + float(ask_high))/2, "lastTraded": None}, 
                            "lowPrice": {"bid": float(bid_low), "ask": float(ask_low), "mid": (float(bid_low) + float(ask_low))/2, "lastTraded": None}, 
                            "lastTradedVolume": int(vol)}
                        self.typical_price(new_30_min,"mid")
                        self.price_spread(new_30_min)
 
                        i = next((index for (index, d) in enumerate(self.prices['MINUTE_30']) if d["snapshotTime"] == timestamp_30), None)
                        if i==None:
                            # update the previous bar with last bars
                            last_period = self.prices['MINUTE_30'][-1]
                            last_timestamp = last_period['snapshotTime']
                            i = next((index for (index, d) in enumerate(self.prices['MINUTE_5']) if d["snapshotTime"] == last_timestamp), None)
                            mins = self.prices['MINUTE_5'][i:]
                            open_price = mins[0]['openPrice']
                            close_price = mins[-1]['closePrice']
                            vol = sum([x['lastTradedVolume'] for x in mins])
                            ask_low = min([x['lowPrice']['ask'] for x in mins])
                            ask_high = max([x['highPrice']['ask'] for x in mins])
                            bid_low = min([x['lowPrice']['bid'] for x in mins])
                            bid_high = max([x['highPrice']['bid'] for x in mins])
                            last_period['closePrice'] = close_price
                            last_period['openPrice'] = open_price
                            last_period['highPrice']['bid'] = bid_high
                            last_period['highPrice']['ask'] = ask_high
                            last_period['highPrice']['mid'] = (bid_high+ask_high)/2

                            last_period['lowPrice']['bid'] = bid_low
                            last_period['lowPrice']['ask'] = ask_low
                            last_period['lowPrice']['mid'] = (bid_low+ask_low)/2
                            last_period['lastTradedVolume'] = int(vol)

                            
                            self.typical_price(last_period,"mid")
                            self.price_spread(last_period)
                            # self.prices['MINUTE_30'][-1] = last_30_min

                            for s in self.strategies.values():
                                s.slow_signals(self,self.prices['MINUTE_30'],'MINUTE_30')
                                s.fast_signals(self,self.prices['MINUTE_5'],'MINUTE_5')

           

                            self.prices["MINUTE_30"].append(new_30_min)

                        else:
                            
                            self.prices["MINUTE_30"][i] = {**self.prices["MINUTE_30"][i], **new_30_min}
                            for s in self.strategies.values():
                                s.fast_signals(self,self.prices['MINUTE_5'],'MINUTE_5')
                          

                        if len(self.prices['MINUTE_30']) > 120:
                            del self.prices['MINUTE_30'][0]

                    
                    self.save_prices()
                    
                else:
                    self.prices['MINUTE_5'][i] = current_price
                    
                if len(self.prices['MINUTE_5'])>120:
                    del self.prices['MINUTE_5'][0]
                    

                

            else:
                self.prices['MINUTE_5'] = []
            
            
            
                
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info("{} live fail".format(self.epic))
            logger.info(exc_type)
            logger.info(fname)
            logger.info(exc_tb.tb_lineno)
            logger.info(exc_obj)
            pass



    def get_update_cost(self, resolution = None, count = 0):
        # if no resolution supplied, return the cost to update everything to the existing depth
        if resolution == None:
            resolutions = self.prices.keys()
            total = 0
            for res in resolutions:
                total+=self.get_update_cost(res)
            return total
        else:
            if resolution in self.prices:
                # default to current depth unless supplied count is greater than 0
                data_count = len(self.prices[resolution])
                if count>0:
                    data_count = count

                time_now = datetime.datetime.now(timezone('GB')).replace(tzinfo=None)
                last_date = datetime.datetime.strptime(self.prices[resolution][-1]['snapshotTime'], "%Y:%m:%d-%H:%M:%S").replace(tzinfo=None)

                delta = time_now - last_date

                seconds_per_unit = 0
                if "MINUTE_5" in resolution:
                    seconds_per_unit = 60
                elif "HOUR" in resolution:
                    seconds_per_unit = 60 * 60
                else:
                    seconds_per_unit = 60 * 60 * 24
                
                if "_" in resolution:
                    multiplier = int(resolution.split("_")[1])
                    seconds_per_unit *= multiplier

                # now see how many times delta.seconds fits into seconds_per_unit
                times_into = divmod(delta.seconds,seconds_per_unit)
                
                data_count = min(times_into[0],data_count)
                if "DAY" in resolution:
                    data_count = delta.days
                
                # limit to data_count value
                
                return data_count
            
            # nothing in memory, just return the given count
            return count

    def update_prices(self, resolution, count = 50):
        data_count = count
        if resolution in self.prices:
            data_count = self.get_update_cost(resolution,count)
            del self.prices[resolution][:data_count]
        else:
            self.prices[resolution] = []
        
        # if needed get new data for our array
        api_calls ={'remainingAllowance':0, 'totalAllowance':0, 'allowanceExpiry':0}
        if data_count > 0:
            

            base_url = self.ig.api_url + "/prices/{}/{}/{}".format(self.epic,resolution,data_count)
            auth_r = requests.get(base_url,headers = self.ig.authenticate())
            if auth_r.ok:
                d = json.loads(auth_r.text)
                self.prices[resolution].extend(d['prices'])
                api_calls = d['allowance']

            else:
                logger.info("WE MIGHT BE FUCKED")
                logger.info(auth_r.status_code)
                logger.info(auth_r.reason)
                logger.info(auth_r.content)

                # kill all trades that are in waiting and put a timeout on this market
                self.cooldown = datetime.datetime.now(timezone('GB')).replace(tzinfo=None) + datetime.timedelta(minutes = 10)
                # for t in self.trades:
                #     if t.state==0:
                #         self.remove_trade(t)
        
        # sanitise the price data incase it contains a None type because of retardation at IG
        self.sanitise_prices(resolution)
        
        # process our strategies
        for s in self.strategies.values():
            if resolution=="MINUTE_30":
                s.slow_signals(self,self.prices[resolution],resolution)
            elif resolution=="MINUTE_5":
                s.fast_signals(self,self.prices[resolution],resolution)
        

        if data_count > 0:
            logger.info("{} updated: used api calls {} remaining {}/{} - time till reset {}".format(self.epic, data_count, api_calls['remainingAllowance'], api_calls['totalAllowance'], self.humanize_time(api_calls['allowanceExpiry'])))

        self.save_prices()

        return self.prices[resolution]


    def sanitise_prices(self,resolution):
        """Checks for None values in price data and sets to previous value"""
        price_groups = ['openPrice','closePrice','highPrice','lowPrice']
        now = self.prices[resolution][0]
        for g in price_groups:
            bid = now[g]['bid']
            ask = now[g]['ask']
            if bid is None:
                bid = self.prices[resolution][1][g]['bid']
            if ask is None:
                ask = self.prices[resolution][1][g]['ask']
            now[g]['bid'] = bid
            now[g]['ask'] = ask

            mid = (bid + ask)/2
            now[g]['mid'] = mid
    
        self.price_spread(now)
        self.typical_price(now,"mid")
        prev = now

        for i in range(1,len(self.prices[resolution])):
            now = self.prices[resolution][i]
            for g in price_groups:
                bid = now[g]['bid']
                ask = now[g]['ask']
                if bid is None:
                    bid = prev[g]['bid']
                if ask is None:
                    ask = prev[g]['ask']
                now[g]['bid'] = bid
                now[g]['ask'] = ask
                
                mid = (bid + ask)/2
                now[g]['mid'] = mid
            
            self.price_spread(now)
            self.typical_price(now,"mid")
            prev = now
            
    def price_spread(self,bar):
        price_groups = ['openPrice','closePrice','highPrice','lowPrice']
        for g in price_groups:
            bar[g]['spread'] = bar[g]['ask'] - bar[g]['bid']

    def typical_price(self,bar,price):
        """ bar - a single price point
            price - "ask", "bid", "mid"
        """
        low = bar['lowPrice'][price]
        high = bar['highPrice'][price]
        closeP = bar['closePrice'][price]
        if 'typicalPrice' not in bar:
            bar['typicalPrice'] = {}
        bar['typicalPrice'][price] = (low + high + closeP)/3

    def perform_regression(self, x, y,mins=5):
        epoch = datetime.datetime.strptime("2010-01-01","%Y-%m-%d")
        x = np.asarray(x)
        y = np.asarray(y)

        # yExp = self.ExpMovingAverage(y,20)
        A = np.vstack([x, np.ones(len(x))]).T

        # print(yExp)
        reg_data = np.linalg.lstsq(A, y)
        m, c = reg_data[0]
        model, resid = reg_data[:2]

        r2 = 1 - resid / (y.size * y.var())

        future_time = datetime.datetime.now().replace(tzinfo=None) + datetime.timedelta(minutes=mins)

        prediction_point = future_time - epoch.replace(tzinfo=None)


        prediction = (m * prediction_point.total_seconds()) + c


        return prediction, m, c
    
    def linear_regression(self, resolutions = None, price_compare = "bid"):


        price_data = {}
        if resolutions is None:
            resolutions = self.prices.keys()
        x = []
        y = []
        for res in resolutions:
            for p in self.prices[res]:
                x.append([float(p['highPrice'][price_compare]),float(p['lowPrice'][price_compare])])
                y.append(float(p['closePrice'][price_compare]))

        
        


    def get_ordered_prices(self, group="closePrice", price = "bid", resolutions=None):
        price_data = {} # will be {time_int:price} - repeated units will be overwritten
        if resolutions==None:
            resolutions = "DAY, HOUR_4, HOUR_3, HOUR_2, HOUR, MINUTE_30, MINUTE_15, MINUTE_10, MINUTE, MINUTE_3, MINUTE_2, MINUTE_5".split(", ")
        
        epoch = datetime.datetime.strptime("2010-01-01","%Y-%m-%d")
        for res in resolutions:
            for p in self.prices[res]:
                
                timestamp = datetime.datetime.strptime(p['snapshotTime'], "%Y:%m:%d-%H:%M:%S")
                diff = timestamp - epoch
                time_int = int(diff.total_seconds())
                price_data[time_int] = [float(p[group][price]),float(p['lastTradedVolume']),timestamp]
                # price_data[time_int] = float(p['closePrice']['bid'])

        x = []
        y = []
        # make sure the prices are in the right order and push into x y
        for key in sorted(price_data):
            x.append(key)
            y.append(price_data[key])
        
        

        return x, y

    def humanize_time(self, secs):
        mins, secs = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        days, hours = divmod(hours, 24)
        return '%02d:%02d:%02d:%02d' % (days, hours, mins, secs)   

    def save_json(self):
        """Saves an overview object in the filesystem - maybe we'll add prices to this, don't want to create overhead for now
            Actually may only really need to save the prices as the other stuff is free to generate and can be updated easily
        """
        
         
        save = {
            "epic" : self.epic,
            "bid"  : self.bid,
            "offer" : self.offer,
            "spread" : self.spread,
            "high" : self.high,
            "low" : self.low,
            "percentage_change" : self.percentage_change,
            "net_change" : self.net_change,
            "market_status" : self.market_status,
            "stop_loss" : self.minimum_stop,
            "data" : self.data
        }
        if not os.path.exists("markets/"):
                os.makedirs("markets/")
        fh = open("markets/" + self.epic + ".json","w")
        json.dump(save,fh)
        fh.close()


    def load_prices(self):
        if os.path.exists("markets/prices/"):
            filepath = "markets/prices/" + self.epic + ".json"
            if os.path.isfile(filepath):
                try:
                    fh = open(filepath,'r')
                    data = json.load(fh)
                    logger.info("found old data, loading")
                    self.prices = data['prices'].copy()
                except Exception as e:
                    logger.info("{} couldn't load JSON {}".format(self.epic,e))
                    self.prices = {}

    def save_prices(self):
        save = {
            "prices" : self.prices.copy()
        }
        if not os.path.exists("markets/prices/"):
                os.makedirs("markets/prices/")
        fh = open("markets/prices/" + self.epic + ".json","w")
        json.dump(save.copy(),fh)
        fh.close()
