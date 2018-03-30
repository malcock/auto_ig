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
        self.rsi = {}
        self.ema = {}

        self.signals = []
        
        self.load_prices()
        self.update_market(market_data)
        try:
            self.current_rsi = float(self.prices['MINUTE_5'][-1]["rsi"])
        except Exception:
            self.current_rsi = 0

    def update_market(self, obj = None):
        if obj is None:
            logger.info("getting " + self.epic + " market data")
            base_url = self.ig.api_url + '/markets/' + self.epic
            auth_r = requests.get(base_url, headers=self.ig.authenticate())
            obj = json.loads(auth_r.text)
        # maybe we can load some prices?
        self.bid = obj['snapshot']['bid']
        self.offer = obj['snapshot']['offer']
        self.spread = float(self.offer) - float(self.bid)
        self.high = obj['snapshot']['high']
        self.low = obj['snapshot']['low']
        self.percentage_change = obj['snapshot']['percentageChange']
        self.net_change = obj['snapshot']['netChange']
        self.market_status = obj['snapshot']['marketStatus']

        # if this market isn't tradeable, remove all price data - it's a dawn of a brand new day!
        if not self.market_status=="TRADEABLE":
            self.prices = {}
            self.save_prices()


    def make_prediction(self, signal):

        # self.update_prices("MINUTE_30",30)
        low_range, max_range, atr_latest = self.average_true_range("MINUTE_30")
        stop = 30
        if signal.action == "BUY":
            # GO LONG
            DIRECTION_TO_TRADE = "BUY"
            DIRECTION_TO_CLOSE = "SELL"
            DIRECTION_TO_COMPARE = 'bid'
            low = min([x['lowPrice']['bid'] for x in self.prices[signal.resolution][:-5]])
            stop = abs(self.bid - low)
            stop = abs(self.bid - self.prices[signal.resolution][-2]['lowPrice']['bid'])

            

        else:
            # GO SHORT!
            DIRECTION_TO_TRADE = "SELL"
            DIRECTION_TO_CLOSE = "BUY"
            DIRECTION_TO_COMPARE = 'offer'
            high = max([x['highPrice']['ask'] for x in self.prices[signal.resolution][:-5]])
            stop = abs(high - self.offer)
            stop = abs(self.prices[signal.resolution][-2]['highPrice']['ask'] - self.offer)

        support = 0
        resistance = 0
        origstop = stop
        stop = min(30,stop)
        stop = max(stop,5)
        # prepare the trade info object to pass back
        prediction_object = {
            "direction_to_trade" : DIRECTION_TO_TRADE,
            "direction_to_close" : DIRECTION_TO_CLOSE,
            "direction_to_compare" : DIRECTION_TO_COMPARE,
            "atr_low" : low_range,
            "atr_max" : max_range,
            "atr_latest": atr_latest,
            "stoploss" : stop,
            "orig_stop" : origstop,
            "limit_distance" : 12,
            "support" : support,
            "resistance" : resistance,
            "signal" : {
                "snapshot_time":signal.snapshot_time,
                "type" : signal.type,
                "action" : signal.action,
                "comment" : signal.comment
            }
            
        }

        return prediction_object
    
    def average_true_range(self, res):
        previous_day = self.prices[res][0]
        prev_close = float(previous_day['closePrice']['bid'])

        tr_prices = []

        for p in self.prices[res][1:]:
            high_price = float(p['highPrice']['bid'])
            low_price = float(p['lowPrice']['bid'])
            price_range = high_price - low_price

            tr = max(price_range, abs(high_price-prev_close), abs(low_price-prev_close))
            tr_prices.append(tr)

            prev_close = p['closePrice']['bid']

        max_range = max(tr_prices)
        low_range = min(tr_prices)

        atr = np.mean(self.rolling_window(np.asarray(tr_prices),14),axis=1)
        diff = len(self.prices[res]) - atr.size
        for i in range(diff,len(self.prices[res])):
            self.prices[res][i]['atr'] = atr[i-diff]
        # low_range = max(low_range,3)

        return int(low_range), int(max_range), atr[-1]

    def set_latest_price(self,values):
        # if self.ready:
        try:
            timestamp = datetime.datetime.fromtimestamp(int(values['UTM'])/1000,timezone('GB')).strftime("%Y:%m:%d-%H:%M:00")
            minNum = datetime.datetime.fromtimestamp(int(values['UTM'])/1000).strftime("%M") #1 or 6? make a new MIN_5
            
            # logger.info(values)
            self.bid = float(values['BID_CLOSE'])
            self.offer = float(values['OFR_CLOSE'])
            self.high = float(values['DAY_HIGH'])
            self.low = float(values['DAY_LOW'])
            self.spread = float(self.offer) - float(self.bid)
            # create an empty price object that matches the hsitorical one
            current_price = {
                    "snapshotTime": timestamp, 
                    "openPrice": {"bid": float(values['BID_OPEN']), "ask": float(values['OFR_OPEN']), "lastTraded": None}, 
                    "closePrice": {"bid": float(values['BID_CLOSE']), "ask": float(values['OFR_CLOSE']), "lastTraded": None }, 
                    "highPrice": {"bid": float(values['BID_HIGH']), "ask": float(values['OFR_HIGH']), "lastTraded": None}, 
                    "lowPrice": {"bid": float(values['BID_LOW']), "ask": float(values['OFR_LOW']), "lastTraded": None}, 
                    "lastTradedVolume": int(values['LTV'])}
            

            if "MINUTE_5" in self.prices:
                # use the timestamp to save the value to the right minute object in the list or make a new one
                i = next((index for (index, d) in enumerate(self.prices['MINUTE_5']) if d["snapshotTime"] == timestamp), None)
                if i==None:
                    self.prices['MINUTE_5'].append(current_price)
                    

                    if "MINUTE_30" in self.prices:
                        last_30_min = int(30 * math.floor(float(minNum)/30))
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
                            "openPrice": {"bid": float(open_price['bid']), "ask": float(open_price['ask']), "lastTraded": None}, 
                            "closePrice": {"bid": float(close_price['bid']), "ask": float(close_price['ask']), "lastTraded": None }, 
                            "highPrice": {"bid": float(bid_high), "ask": float(ask_high), "lastTraded": None}, 
                            "lowPrice": {"bid": float(bid_low), "ask": float(ask_low), "lastTraded": None}, 
                            "lastTradedVolume": int(vol)}

                        i = next((index for (index, d) in enumerate(self.prices['MINUTE_30']) if d["snapshotTime"] == timestamp_30), None)
                        if i==None:
                            self.calculate_indicators('MINUTE_30')

                            price_len = len(self.prices['MINUTE_30'])
                            # only want to analyse the last 4 price points (2 hrs)

                            for p in range(price_len-5,price_len):
                                self.detect_rsi("MINUTE_30",p)
                                self.detect_stochastic("MINUTE_30",p)
                            for p in range(price_len-1,price_len):
                                # self.detect_psar('MINUTE_30',p)
                                self.detect_crossover('MINUTE_30',p)
                                # self.detect_macd("MINUTE_30",p)
                                # self.detect_ma50_cross('MINUTE_30',p)

                            self.prices["MINUTE_30"].append(new_30_min)

                            trades = [x for x in self.ig.trades if x.market.epic == self.epic]
                            for t in trades:
                                t.update_interval("MINUTE_30")
                        else:
                            

                            self.prices["MINUTE_30"][i] = new_30_min
                            

                        if len(self.prices['MINUTE_30']) > 75:
                            del self.prices['MINUTE_30'][0]

                        self.calculate_indicators('MINUTE_30')
                        price_len = len(self.prices['MINUTE_30'])
                        # only want to analyse the last 4 price points (2 hrs)

                        for p in range(price_len-5,price_len):
                            self.detect_rsi("MINUTE_30",p)
                            self.detect_stochastic("MINUTE_30",p)
                        for p in range(price_len-1,price_len):
                            # self.detect_psar('MINUTE_30',p)
                            self.detect_crossover('MINUTE_30',p)

                        

                    # if signal.update returns False, remove from list
                    for s in self.signals:
                        if not s.update(self):
                            self.signals.remove(s)    

                    self.save_prices()
                    
                else:
                    self.prices['MINUTE_5'][i] = current_price
                    
                if len(self.prices['MINUTE_5'])>75:
                    del self.prices['MINUTE_5'][0]
                    
                self.calculate_rsi('MINUTE_5')
                

                self.current_rsi = float(self.prices['MINUTE_5'][-1]["rsi"])

                

            else:
                self.prices['MINUTE_5'] = []
            
            

                
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info(exc_type, fname, exc_tb.tb_lineno,exc_obj)
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
                # time_now = .localize(time_now)
                # last_date = .localize(last_date)
                print("res {}, last date: {}, now: {}".format(resolution, last_date,time_now))
                delta = time_now - last_date
                print(delta)
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

                # now see how many times delta.seconds fits into seconds_per_unit
                times_into = divmod(delta.seconds,seconds_per_unit)
                print(times_into)
                # limit to data_count value
                data_count = min(times_into[0],data_count)
                print("required:{}".format(data_count))
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
        # self.sanitise_prices(resolution)
        # whether we updated prices or not, lets recalculate our rsi and emas
        self.calculate_indicators(resolution)

        # price_len = len(self.prices[resolution])
        # # only want to analyse the last 30 price points (reduce to 10 later)
        # for p in range(price_len-40,price_len):
        #     self.analyse_candle(resolution, p)

        logger.info("{} updated: used api calls {} remaining {}/{} - time till reset {}".format(self.epic, data_count, api_calls['remainingAllowance'], api_calls['totalAllowance'], self.humanize_time(api_calls['allowanceExpiry'])))

        self.save_prices()

        return self.prices[resolution]


    def sanitise_prices(self,resolution):
        """Checks for None values in price data and sets to previous value"""
        price_groups = ['openPrice','closePrice','highPrice','lowPrice']
        price_types = ['bid','ask']
        for g in price_groups:
            for t in price_types:
                prices = [x[g][t] for x in self.prices[resolution]]
                none_indices = [i for i,val in enumerate(prices) if val is None]
                if len(none_indices)>0:
                    for i in none_indices:
                        if i>0:
                            self.prices[resolution][g][t][i] = self.prices[resolution][g][t][i-1]
                        else:
                            self.prices[resolution][g][t][i] = 0

    # ********* Candlestick detection ************
    def analyse_candle(self, resolution, index):
        point = self.prices[resolution][index]
        high_price = float(point['highPrice']['bid'])
        low_price = float(point['lowPrice']['bid'])
        open_price = float(point['openPrice']['bid'])
        close_price = float(point['closePrice']['bid'])
        point['movement'] = close_price - open_price
        # self.detect_hammer(resolution,index, high_price, low_price, open_price, close_price)
        # self.detect_crossover(resolution,index)
        self.detect_rvi(resolution,index)
        self.detect_macd(resolution,index)

    def detect_rvi(self,resolution,index):
        if index<20:
            return
        
        now = self.prices[resolution][index]['rvi_histogram']
        prev = self.prices[resolution][index-1]['rvi_histogram']
        delta = abs(prev - now)

        if now > 0 and prev < 0:
            position = "BUY"
        elif now < 0 and prev > 0:
            position = "SELL"
        else:
            # no cross over, don't continue - we may want to expand this later for predicting 
            return

        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"RVI",delta,"delta:{}".format(delta))
    


    def detect_macd_0(self,resolution, index):
        """detects the macd line cross 0"""
        now = self.prices[resolution][index]['macd']
        prev = self.prices[resolution][index-1]['macd']

        if now > 0 and prev < 0:
            position = "BUY"
        elif now < 0 and prev > 0:
            position = "SELL"
        else:
            return

        delta = abs(prev - now)

        comment = "MACD 0 Crossover"
        confirmed = True
        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"MACD",delta,comment,confirmed)

    def detect_macd(self, resolution, index):
        """detects a macd signal - assigns strong if the previous rsi shows strong, but not too strong"""
        
        

        now = self.prices[resolution][index]['macd_histogram']
        prev = self.prices[resolution][index-1]['macd_histogram']
        
        # figure out of theres a cross over
        if now > 0 and prev < 0:
            position = "BUY"
            confirmation_price = max(2,now*2)
        elif now < 0 and prev > 0:
            position = "SELL"
            confirmation_price = min(-2,now*2)
        else:
            # no cross over, don't continue - we may want to expand this later for predicting 
            return

        delta = abs(prev - now)

        last_rsi = [x['rsi'] for x in self.prices[resolution][index-10:index]]
        prev_rsi = sum(last_rsi)/len(last_rsi)
        
        comment = "Basic MACD signal"
        # check our signals for a previous matching RVI signal
        rvi_sigs = sorted([x for x in self.signals if (x.type=="RVI" and x.action==position)], key=operator.attrgetter('snapshot_time'), reverse=True)
        confirmed = False
        if len(rvi_sigs)>0:
            r = self.prices[resolution][-1]['rsi']
            yes = False
            if r > 52.5 and position=="BUY":
                if self.prices[resolution][index]['macd']>0:
                    yes = True
            if r < 47.5 and position=="SELL":
                if self.prices[resolution][index]['macd']<0:
                    yes = True

            
            if yes:
                confirmed = True
                comment = "MACD confirmed by RSI {} RVI at {}".format(r,rvi_sigs[0].snapshot_time)
            else:
                comment = "MACD only confirmed by RVI at {} but not RSI {}".format(rvi_sigs[0].snapshot_time,r)
            

        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"MACD",delta,comment,confirmed)

        
    def detect_rsi(self,resolution,index):
        """detect when RSI goes back into normal ranges after being over sold or bought"""
        now = self.prices[resolution][index]['rsi']
        prev = self.prices[resolution][index-1]['rsi']

        oversold = 29
        overbought = 69
        # figure out of theres a cross over
        if now > oversold and prev <= oversold:
            position = "BUY"
            comment = "RSI crossed back from oversold"
        elif now < overbought and prev >= overbought:
            position = "SELL"
            comment = "RSI crossed back from overbought"
        else:
            # no cross over, don't continue - we may want to expand this later for predicting 
            return
        
        delta = now - prev

        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"RSI",delta,comment)
    
    def detect_stochastic(self,resolution,index):
        """detect when stoch goes back from over sold or bought position"""
        now = self.prices[resolution][index]['stoch_k']
        prev = self.prices[resolution][index-1]['stoch_k']

        oversold = 20
        overbought = 80
        # figure out of theres a cross over
        if now > oversold and prev <= oversold:
            position = "BUY"
            comment = "Stochastic crossed back from oversold"
        elif now < overbought and prev >= overbought:
            position = "SELL"
            comment = "Stochastic crossed back from overbought"
        else:
            # no cross over, don't continue - we may want to expand this later for predicting 
            return
        
        delta = now - prev

        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"STOCH",delta,comment)

    def detect_psar(self, resolution, index):
        now = self.prices[resolution][index]['psar_bull']
        prev = self.prices[resolution][index-1]['psar_bull']
        print("psar! {} {}".format(now,prev))
        if now != ''  and prev =='':
            position = "BUY"
            comment = "psar flipped to BULL"
        elif now == '' and prev !='':
            position = "SELL"
            comment = "psar flipped to BEAR"
        else:
            return

        # check if we have a previous stoch and rsi signals
        confirmed = False
        rsi_sigs = [x for x in self.signals if (x.type=="RSI" and x.action == position)]
        stoch_sigs = [x for x in self.signals if (x.type=="STOCH" and x.action == position)]
        delta = 1
        if len(rsi_sigs)>0 and len(stoch_sigs) > 0:
            confirmed = True
            comment += " confirmed by RSI and STOCH"
        
        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"PSAR",delta,comment,confirmed)

    
    def detect_crossover(self, resolution, index):
        """Detect a crossover of the wma_5 and wma_10 data"""
        now_diff = self.prices[resolution][index]['wma_5'] - self.prices[resolution][index]['wma_10']
        prev_diff = self.prices[resolution][index-1]['wma_5'] - self.prices[resolution][index-1]['wma_10']
        
        position = None
        if now_diff>0 and prev_diff<0:
            position = "BUY"
        
        if now_diff<0 and prev_diff>0:
            position = "SELL"

        if position is None:
            return

        delta = now_diff - prev_diff
        comment = "prev:{}, now: {}".format(prev_diff,now_diff)
        confirmed = False
        rsi_sigs = [x for x in self.signals if (x.type=="RSI" and x.action == position)]
        stoch_sigs = [x for x in self.signals if (x.type=="STOCH" and x.action == position)]
        delta = 1
        if len(rsi_sigs)>0 and len(stoch_sigs) > 0:
            confirmed = True
            comment += " confirmed by RSI and STOCH"
        

        
        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"CROSSOVER",delta,comment,confirmed)
        

    # def detect_hammer(self, resolution, index, high_price, low_price, open_price, close_price):
    #     """Detect a hammer candlestick"""
    #     point = self.prices[resolution][index]
    #     size = high_price - low_price
    #     if size ==0:
    #         return
    #     body_top = max(open_price, close_price)
    #     body_bottom = min(open_price, close_price)
    #     body_size = body_top - body_bottom
    #     top_shadow = (high_price - body_top)/size
    #     bottom_shadow = (body_bottom - low_price)/size
    #     big_shadow = max(top_shadow,bottom_shadow)
    #     small_shadow = min(top_shadow, bottom_shadow)
    #     body_percent = body_size/size
    #     if (body_percent<0.40 and big_shadow>small_shadow*1.25):
    #         # possible hammer detected, decide initial signal position
    #         position = "BUY"
    #         if point['ema_12'] > point['ema_26']:
    #             position = "SELL"
            
    #         # now check backwards to see if it's part of a trend
    #         trend_check = self.prices[resolution][index-10:index]
    #         trend_ok = True
    #         for p in trend_check:
 
    #             p_position = "BUY"
    #             if p['ema_12'] > p['ema_26']:
    #                 p_position = "SELL"
    #             if position != p_position:
    #                 trend_ok = False
    #                 break
            
    #         if trend_ok:
    #             if position=="BUY":
    #                 confirmation_price = body_top + (big_shadow*size)
    #             else:
    #                 confirmation_price = body_bottom - (big_shadow*size)

    #             comment = "o:{}, c:{}, h:{}, l:{}".format(open_price,close_price,high_price,low_price)
    #             self.add_signal(resolution,point['snapshotTime'],position,"HAMMER",comment,round(confirmation_price,2))
    def remove_signals(self,resolution, index):
        snapshot_time = self.prices[resolution][index]['snapshotTime']
        matching_signals = [x for x in self.signals if x.snapshot_time==snapshot_time]
        for s in matching_signals:
            self.signals.remove(s)

    def add_signal(self,resolution, snapshot_time, position, signal_type, delta, comment = "", confirmed = False ):
        """Add a signal to the market"""

        # snap_start = datetime.datetime.strptime(snapshot_time, "%Y:%m:%d-%H:%M:%S").replace(tzinfo=None)
        # now = datetime.datetime.now()

        # diff = now - snap_start
        # percent = (diff.seconds/60) / 30
        # if percent < 0.55:
        #     if percent * delta < 0.5:
        #         logger.info("SIGNAL? {} Found {} signal, but delta {} wasn't strong enough at this time {}".format(self.epic,signal_type,delta,now.strftime('"%Y:%m:%d-%H:%M:%S"')))
        #         return
        # remove any previous signals of this type
        matching_signals = [x for x in self.signals if x.type==signal_type]
        for s in matching_signals:
            self.signals.remove(s)

        self.signals.append(Signal(self.epic,resolution,snapshot_time,position,signal_type, comment, confirmed))

    # ********* Indicator calculations ***********
    def calculate_indicators(self, resolution):
        self.wma(resolution,5)
        self.wma(resolution,10)
        self.trend(resolution,'wma_10','wma_10_trend')
        self.moving_average(resolution,5)
        self.moving_average(resolution,10)
        self.calculate_rsi(resolution)
        self.calculate_macd(resolution)
        self.roc(resolution)
        self.calculate_relative_vigor(resolution,10)
        self.average_true_range(resolution)
       
        self.calculate_stochastic(resolution)
        self.psar(resolution)

    def calculate_trend(self, prices):
        """calculates a relative trend based on an arbitary array of data"""
        total = 0
        if len(prices)>0:
            first_time = True
            
            last_value = 0
            iterator = 0
            for p in prices:
                if first_time:
                    last_value = p
                    first_time = False
                else:
                    new_value = p
                    val = (new_value - last_value)
                    total += val
                    last_value = new_value
                iterator+=1
            
            total/=len(prices)
        return total

    def roc(self,resolution, window=12):
        for i in range(window,len(self.prices[resolution])):
            self.prices[resolution][i]['roc'] = ((self.prices[resolution][i]['closePrice']['bid'] - self.prices[resolution][i-window]['closePrice']['bid'])/self.prices[resolution][i-window]['closePrice']['bid'])

    def trend(self,resolution, value, name):
        for i in range(1,len(self.prices[resolution])):
            if value in self.prices[resolution][-i]:
                self.prices[resolution][i][name] = self.prices[resolution][i][value] - self.prices[resolution][i-1][value]

    def calculate_macd(self, resolution):
        self.exponential_average(resolution,12)
        self.exponential_average(resolution,26)
        fast = [x['ema_12'] for x in self.prices[resolution]]
        slow = [x['ema_26'] for x in self.prices[resolution]]
        macd = list(map(operator.sub,fast,slow))
        self.exponential_average(resolution,9,macd,"macd_signal")
        for i in range(0,len(self.prices[resolution])):
            self.prices[resolution][i]['macd'] = macd[i]
            self.prices[resolution][i]['macd_histogram'] = self.prices[resolution][i]['macd'] - self.prices[resolution][i]['macd_signal']
    

    def calculate_relative_vigor(self,resolution, N):
        close_price = [x['closePrice']['bid'] for x in self.prices[resolution]]
        open_price = [x['openPrice']['bid'] for x in self.prices[resolution]]
        high_price = [x['highPrice']['bid'] for x in self.prices[resolution]]
        low_price = [x['lowPrice']['bid'] for x in self.prices[resolution]]
        close_open = list(map(operator.sub,close_price,open_price))

        high_low = list(map(operator.sub,high_price,low_price))
        
        close_open = self.swma(close_open)
        
        high_low = self.swma(high_low)

        close_open = self.rolling_sum(close_open,N)
        high_low = self.rolling_sum(high_low,N)
        

        rvi = np.divide(close_open,high_low)
        sig = self.swma(rvi)
        rvi = rvi[len(rvi) - len(sig):]
        hist = np.subtract(rvi,sig)
        

        price_len = len(self.prices[resolution])
        diff = price_len - len(sig)
        
        for i in range(diff,price_len):
            self.prices[resolution][i]['rvi'] = rvi[i-diff]
            self.prices[resolution][i]['rvi_signal'] = sig[i-diff]
            self.prices[resolution][i]['rvi_histogram'] = hist[i-diff]

    def rolling_sum(self, a, n=4) :
        ret = np.cumsum(a, dtype=float)
        ret[n:] = ret[n:] - ret[:-n]
        return ret[n - 1:]


    def sum(self,x,N):
        return np.sum(self.rolling_window(x,N))


    def swma(self,x):
        a = np.asarray(x)
        roll = self.rolling_window(a,4)
        # print(roll)
        return np.average(roll,axis=1,weights= [1/6, 2/6, 2/6, 1/6])

    def rolling_window(self,a, window):
        shape = a.shape[:-1] + (a.shape[-1] - window + 1, window)
        strides = a.strides + (a.strides[-1],)
        return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)

    def simple_moving_average(self, x, N, name=None):
        cumsum = np.cumsum(np.insert(x, 0, 0)) 
        return (cumsum[N:] - cumsum[:-N]) / float(N)

    def psar(self,resolution, iaf = 0.02, maxaf = 0.2):
        barsdata = self.prices[resolution]
        length = len(barsdata)
        dates = [x['snapshotTime'] for x in barsdata]
        high = [x['highPrice']['bid'] for x in barsdata]
        low = [x['lowPrice']['bid'] for x in barsdata]
        close = [x['closePrice']['bid'] for x in barsdata]
        psar = close[0:len(close)]
        psarbull = [None] * length
        psarbear = [None] * length
        bull = True
        af = iaf
        ep = low[0]
        hp = high[0]
        lp = low[0]

        
        for i in range(2,length):
            if bull:
                psar[i] = psar[i - 1] + af * (hp - psar[i - 1])
            else:
                psar[i] = psar[i - 1] + af * (lp - psar[i - 1])
            
            reverse = False
            
            if bull:
                if low[i] < psar[i]:
                    bull = False
                    reverse = True
                    psar[i] = hp
                    lp = low[i]
                    af = iaf
            else:
                if high[i] > psar[i]:
                    bull = True
                    reverse = True
                    psar[i] = lp
                    hp = high[i]
                    af = iaf
        
            if not reverse:
                if bull:
                    if high[i] > hp:
                        hp = high[i]
                        af = min(af + iaf, maxaf)
                    if low[i - 1] < psar[i]:
                        psar[i] = low[i - 1]
                    if low[i - 2] < psar[i]:
                        psar[i] = low[i - 2]
                else:
                    if low[i] < lp:
                        lp = low[i]
                        af = min(af + iaf, maxaf)
                    if high[i - 1] > psar[i]:
                        psar[i] = high[i - 1]
                    if high[i - 2] > psar[i]:
                        psar[i] = high[i - 2]
                        
            if bull:
                psarbull[i] = psar[i]
                self.prices[resolution][i]['psar_bull'] = psar[i]
                self.prices[resolution][i]['psar_bear'] = ''
            else:
                psarbear[i] = psar[i]
                self.prices[resolution][i]['psar_bear'] = psar[i]
                self.prices[resolution][i]['psar_bull'] = ''

        return {"dates":dates, "high":high, "low":low, "close":close, "psar":psar, "psarbear":psarbear, "psarbull":psarbull}


  
    def calculate_trailing(self, resolution):
        # highs = np.asarray([x['highPrice']['bid'] for x in self.prices[resolution][-40]]).reshape((5,-1)).amax(axis=1)
        # lows = np.asarray([x['lowPrice']['ask'] for x in self.prices[resolution][-40]]).reshape((5,-1)).amin(axis=1)
        try:
            price_len = len(self.prices[resolution]) 
 
            high_data = list(self.get_ordered_prices("highPrice","ask",[resolution])) 
            low_data = list(self.get_ordered_prices("lowPrice","bid",[resolution])) 
    
            high_data_compile = [] 
            low_data_compile = [] 
    
            for p in range(0,len(high_data[0])): 
    
                high_data_compile.append([high_data[0][p], high_data[1][p]]) 
                low_data_compile.append([low_data[0][p], low_data[1][p]]) 

            for i in range(price_len-5,price_len): 
            
                high_data_seg = high_data_compile[i-20:i] 
                low_data_seg = low_data_compile[i-20:i] 
                
                
                highs = [] 
                lows = [] 
                for chunk in list(self.chunks(high_data_seg,4)): 
                    # print(chunk) 
                    h = max(chunk, key=lambda x:x[1][0]) 
                    highs.append(h) 
                
                for chunk in list(self.chunks(low_data_seg,4)): 
                    # print(chunk) 
                    l = min(chunk,key=lambda x:x[1][0]) 
                    lows.append(l) 
    
                # print("highs: {} {}".format(i, highs)) 
                # print("lows: {} {}".format(i, lows)) 
                h_x = [x[0] for x in highs] 
                h_y = [y[1][0] for y in highs] 
                l_x = [x[0] for x in lows] 
                l_y = [y[1][0] for y in lows] 
    
    
                h_p, h_m, h_c = self.perform_regression(h_x,h_y) 
                l_p, l_m, l_c = self.perform_regression(l_x,l_y) 
    
                if h_m>0: 
                    h_p = max(h_y) 
                    
                    
                if l_m<0: 
                    l_p = min(l_y) 
                    
    
                self.prices[resolution][i]["high_trail"] = h_p 
                self.prices[resolution][i]["low_trail"] = l_p

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            logger.info(exc_type, fname, exc_tb.tb_lineno,exc_obj)
            pass
        

    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i + n]

    def calculate_stochastic(self,resolution, length=5, smoothK=3, smoothD = 3):
        """Calculate stochastic indicator for timeframe"""

        def stoch(close,highs,lows):
            high = np.max(highs)
            low = np.min(lows)
            close = close[-1]
            k =((close - low)/(high - low)) * 100
            return k

        highs = self.rolling_window(np.asarray([x['highPrice']['bid'] for x in self.prices[resolution]]),length)
        lows = self.rolling_window(np.asarray([x['lowPrice']['bid'] for x in self.prices[resolution]]),length)
        closes = self.rolling_window(np.asarray([x['closePrice']['bid'] for x in self.prices[resolution]]),length)
        ks = []
        for i in range(0,len(closes)):
            ks.append(stoch(closes[i],highs[i],lows[i]))


        k = self.moving_average(resolution,smoothK,values = ks,save = False)
        d = self.moving_average(resolution,smoothD,values=k, save=False)

        k = k[len(k) - len(d):]

        price_len = len(self.prices[resolution])
        diff = price_len - len(d)
        
        for i in range(diff,price_len):
            self.prices[resolution][i]['stoch_k'] = k[i-diff]
            self.prices[resolution][i]['stoch_d'] = d[i-diff]

        


    def calculate_rsi(self, resolution, n=9):
        """Calculate the RSI"""
        prices = np.asarray([x['closePrice']['bid'] for x in self.prices[resolution]])

        deltas = np.diff(prices)
        seed = deltas[:n+1]
        up = seed[seed>=0].sum()/n
        down = -seed[seed<0].sum()/n
        rs = up/down
        rsi = np.zeros_like(prices)
        # rsi[:n] = 100. - 100./(1.+rs)
        # rsi[:n] = -1
        
        for i in range(0,n):
            if not "rsi" in self.prices[resolution][i]:
                self.prices[resolution][i]["rsi"] = -1

        for i in range(n, len(prices)):
            delta = deltas[i-1] # cause the diff is 1 shorter

            if delta>0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta

            up = (up*(n-1) + upval)/n
            down = (down*(n-1) + downval)/n

            rs = up/down
            rsi[i] = 100. - 100./(1.+rs)
            self.prices[resolution][i]["rsi"] = rsi[i]

        return rsi


    def numpy_ewma_vectorized_v2(self, data, window):

        alpha = 2 /(window + 1.0)
        alpha_rev = 1-alpha
        n = data.shape[0]

        pows = alpha_rev**(np.arange(n+1))

        scale_arr = 1/pows[:-1]
        offset = data[0]*pows[1:]
        pw0 = alpha*alpha_rev**(n-1)

        mult = data*pw0*scale_arr
        cumsums = mult.cumsum()
        out = offset + cumsums*scale_arr[::-1]
        return out

    
    def moving_average(self,resolution, window, values = None, name = None, save = True):
        if values is None:
            values = np.asarray([x['closePrice']['bid'] for x in self.prices[resolution]])
        else:
            values = np.asarray(values)

        a  = np.mean(self.rolling_window(values,window),axis=1)

        if save:
            if name is None:
                name = "ma_{}".format(window)

            price_len = len(self.prices[resolution])
            diff = price_len - len(a)
        
            for i in range(diff,price_len):
                self.prices[resolution][i][name] = a[i-diff]
        

        return a



    def wma(self, resolution, window, values= None, name = None, save = True):
        if values is None:
            values = np.asarray([x['closePrice']['bid'] for x in self.prices[resolution]])
        else:
            values = np.asarray(values)
        
        w = range(1,window+1)
        
        a = np.average(self.rolling_window(values,window),axis=1,weights=w)

        if save:
            if name is None:
                name = "wma_{}".format(window)

            price_len = len(self.prices[resolution])
            diff = price_len - len(a)
            
            for i in range(diff,price_len):
                self.prices[resolution][i][name] = a[i-diff]
        

        return a
    

    def exponential_average(self, resolution, window, values= None, name = None):
        if values is None:
            values = np.asarray([x['closePrice']['bid'] for x in self.prices[resolution]])
        else:
            values = np.asarray(values)
        a = self.numpy_ewma_vectorized_v2(values,window)
        # weights = np.exp(np.linspace(1.,0.,window))
        # weights /= weights.sum()

        # a = np.convolve(values, weights) [:len(values)]
        # a[:window]=a[window]
        if name is None:
            name = "ema_{}".format(window)
        # add the ema data to the saved price data
        for i in range(0,len(values)):
            if i < window:
                # in duff pre-window add ema data if the property doesn't exist, leave if not
                if not name in self.prices[resolution][i]:
                    self.prices[resolution][i][name] = a[i]
            else:
                # always add after the window
                self.prices[resolution][i][name] = a[i]
        return a

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
            resolutions = "DAY, HOUR_4, HOUR_3, HOUR_2, HOUR, MINUTE_30, MINUTE_15, MINUTE_10, MINUTE_5, MINUTE_3, MINUTE_2, MINUTE".split(", ")
        
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
            "current_rsi" : self.current_rsi  
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
