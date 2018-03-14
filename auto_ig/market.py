import logging
import os, sys
import datetime
import json
import math
import operator
import requests
import numpy as np

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
        self.cooldown = datetime.datetime(2000,1,1,0,0,0,0,datetime.timezone.utc)
        self.ig = ig_obj
        # raw data and signal producers
        self.prices = {}
        self.rsi = {}
        self.ema = {}

        self.signals = []
        
        self.load_prices()
        self.update_market(market_data)
        try:
            self.current_rsi = float(self.prices['MINUTE'][-1]["rsi"])
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

    def make_prediction(self, signal):

        self.update_prices("HOUR",30)
        low_range, max_range = self.average_true_range("HOUR")

        if signal.action == "BUY":
            # GO LONG
            DIRECTION_TO_TRADE = "BUY"
            DIRECTION_TO_CLOSE = "SELL"
            DIRECTION_TO_COMPARE = 'bid'
        else:
            # GO SHORT!
            DIRECTION_TO_TRADE = "SELL"
            DIRECTION_TO_CLOSE = "BUY"
            DIRECTION_TO_COMPARE = 'offer'

        support = 0
        resistance = 0
        # prepare the trade info object to pass back
        prediction_object = {
            "direction_to_trade" : DIRECTION_TO_TRADE,
            "direction_to_close" : DIRECTION_TO_CLOSE,
            "direction_to_compare" : DIRECTION_TO_COMPARE,
            "atr_low" : low_range,
            "atr_max" : max_range,
            "stoploss" : min(max_range,15),
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

        # low_range = max(low_range,3)

        return int(low_range), int(max_range)

    def set_latest_price(self,values):
        # if self.ready:
        try:
            timestamp = datetime.datetime.fromtimestamp(int(values['UTM'])/1000).strftime("%Y:%m:%d-%H:%M:00")
            minNum = datetime.datetime.fromtimestamp(int(values['UTM'])/1000).strftime("%M") #1 or 6? make a new MIN_5
            logging.info(values)
            self.bid = float(values['BID_CLOSE'])
            self.offer = float(values['OFR_CLOSE'])
            self.spread = float(self.offer) - float(self.bid)
            # create an empty price object that matches the hsitorical one
            current_price = {
                    "snapshotTime": timestamp, 
                    "openPrice": {"bid": float(values['BID_OPEN']), "ask": float(values['OFR_OPEN']), "lastTraded": None}, 
                    "closePrice": {"bid": float(values['BID_CLOSE']), "ask": float(values['OFR_CLOSE']), "lastTraded": None }, 
                    "highPrice": {"bid": float(values['BID_HIGH']), "ask": float(values['OFR_HIGH']), "lastTraded": None}, 
                    "lowPrice": {"bid": float(values['BID_LOW']), "ask": float(values['OFR_LOW']), "lastTraded": None}, 
                    "lastTradedVolume": int(values['LTV'])}
            

            if "MINUTE" in self.prices:
                # use the timestamp to save the value to the right minute object in the list or make a new one
                i = next((index for (index, d) in enumerate(self.prices['MINUTE']) if d["snapshotTime"] == timestamp), None)
                if i==None:
                    self.prices['MINUTE'].append(current_price)

                    if "MINUTE_5" in self.prices:
                        last_5_min = int(5 * math.floor(float(minNum)/5))
                        timestamp_5 = datetime.datetime.fromtimestamp(int(values['UTM'])/1000).strftime("%Y:%m:%d-%H:{:0>2d}:00".format(last_5_min))
                        # get all elements from MINUTE list since last 5min mark
                        i = next((index for (index, d) in enumerate(self.prices['MINUTE']) if d["snapshotTime"] == timestamp_5), None)
                        mins = self.prices['MINUTE'][i:]
                        open_price = mins[0]['openPrice']
                        close_price = mins[-1]['closePrice']
                        vol = sum([x['lastTradedVolume'] for x in mins])
                        ask_low = min([x['lowPrice']['ask'] for x in mins])
                        ask_high = max([x['highPrice']['ask'] for x in mins])
                        bid_low = min([x['lowPrice']['bid'] for x in mins])
                        bid_high = max([x['highPrice']['bid'] for x in mins])
                        new_5_min = {
                            "snapshotTime": timestamp_5, 
                            "openPrice": {"bid": float(open_price['bid']), "ask": float(open_price['ask']), "lastTraded": None}, 
                            "closePrice": {"bid": float(close_price['bid']), "ask": float(close_price['ask']), "lastTraded": None }, 
                            "highPrice": {"bid": float(bid_high), "ask": float(ask_high), "lastTraded": None}, 
                            "lowPrice": {"bid": float(bid_low), "ask": float(ask_low), "lastTraded": None}, 
                            "lastTradedVolume": int(vol)}

                        i = next((index for (index, d) in enumerate(self.prices['MINUTE_5']) if d["snapshotTime"] == timestamp_5), None)
                        if i==None:
                            price_len = len(self.prices['MINUTE_5'])
                            # only want to analyse the last 30 price points (reduce to 10 later)

                            for p in range(price_len-3,price_len):
                                self.analyse_candle('MINUTE_5', p)

                            self.prices["MINUTE_5"].append(new_5_min)

                            trades = [x for x in self.ig.trades if x.market.epic == self.epic]
                            for t in trades:
                                t.update_interval("MINUTE_5")
                        else:
                            

                            self.prices["MINUTE_5"][i] = new_5_min
                            

                        if len(self.prices['MINUTE_5']) > 50:
                            del self.prices['MINUTE_5'][0]

                        self.calculate_rsi('MINUTE_5')
                        

                        self.calculate_macd('MINUTE_5')
                        self.calculate_trailing('MINUTE_5')
                        self.calculate_trailing('MINUTE')

                        self.calculate_macd('MINUTE')

                        

                    self.save_prices()
                    
                else:
                    self.prices['MINUTE'][i] = current_price
                    
                if len(self.prices['MINUTE'])>50:
                    del self.prices['MINUTE'][0]
                    
                self.calculate_rsi('MINUTE')
                

                self.current_rsi = float(self.prices['MINUTE'][-1]["rsi"])

                

            else:
                self.prices['MINUTE'] = []
            
            

                
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno,exc_obj)
            pass

        # if signal.update returns False, remove from list
        for s in self.signals:
            if not s.update(self):
                self.signals.remove(s)


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

                time_now = datetime.datetime.now(datetime.timezone.utc)
                last_date = datetime.datetime.strptime(self.prices[resolution][-1]['snapshotTime'], "%Y:%m:%d-%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                delta = time_now - last_date
                
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

                # limit to data_count value
                data_count = min(times_into[0],data_count)

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
                self.cooldown = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes = 10)
                # for t in self.trades:
                #     if t.state==0:
                #         self.remove_trade(t)

        # whether we updated prices or not, lets recalculate our rsi and emas
        self.calculate_rsi(resolution)
        
        self.calculate_macd(resolution)

        self.calculate_trailing(resolution)

        # price_len = len(self.prices[resolution])
        # # only want to analyse the last 30 price points (reduce to 10 later)
        # for p in range(price_len-40,price_len):
        #     self.analyse_candle(resolution, p)

        logger.info("{} updated: api calls remaining {}/{} - time till reset {}".format(self.epic, api_calls['remainingAllowance'], api_calls['totalAllowance'], self.humanize_time(api_calls['allowanceExpiry'])))

        self.save_prices()

        return self.prices[resolution]

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
        self.detect_macd(resolution,index)

    def detect_macd(self, resolution, index):
        """detects a macd signal - assigns strong if the previous rsi shows strong, but not too strong"""
        if index<20:
            return
        

        now = self.prices[resolution][index]['macd_histogram']
        prev = self.prices[resolution][index-1]['macd_histogram']

        # figure out of theres a cross over
        if now > 0 and prev < 0:
            position = "BUY"
        elif now < 0 and prev > 0:
            position = "SELL"
        else:
            # no cross over, don't continue - we may want to expand this later for predicting 
            return


        is_strong = False
        last_rsi = [x['rsi'] for x in self.prices[resolution][index-10:index]]
        prev_rsi = sum(last_rsi)/len(last_rsi)
        if position == "BUY":
            prev_rsi = min(last_rsi)

            if 28 < prev_rsi < 40:
                is_strong = True

        else:
            prev_rsi = max(last_rsi)

            if 59 < prev_rsi < 72:
                is_strong = True

        # need another check here too of the previous strength of the movement to see if this is a small correction
        
        if is_strong:
            self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"MACD_STRONG","STRONG {} RSI {}".format(position, prev_rsi))
        else:
            self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"MACD_WEAK","WEAK {} RSI {}".format(position,prev_rsi))
     

        
        

    def detect_crossover(self, resolution, index):
        """Detect a crossover of the ema_12 and ema_26 data"""
        now_diff = self.prices[resolution][index]['ema_12'] - self.prices[resolution][index]['ema_26']
        prev_diff = self.prices[resolution][index-1]['ema_12'] - self.prices[resolution][index-1]['ema_26']
        
        position = None
        if now_diff>0 and prev_diff<0:
            position = "BUY"
        
        if now_diff<0 and prev_diff>0:
            position = "SELL"

        if position is None:
            return

        comment = "prev:{}, now: {}".format(prev_diff,now_diff)
        self.add_signal(resolution,self.prices[resolution][index]['snapshotTime'],position,"CROSSOVER",comment)
        

    def detect_hammer(self, resolution, index, high_price, low_price, open_price, close_price):
        """Detect a hammer candlestick"""
        point = self.prices[resolution][index]
        size = high_price - low_price
        if size ==0:
            return
        body_top = max(open_price, close_price)
        body_bottom = min(open_price, close_price)
        body_size = body_top - body_bottom
        top_shadow = (high_price - body_top)/size
        bottom_shadow = (body_bottom - low_price)/size
        big_shadow = max(top_shadow,bottom_shadow)
        small_shadow = min(top_shadow, bottom_shadow)
        body_percent = body_size/size
        if (body_percent<0.40 and big_shadow>small_shadow*1.25):
            # possible hammer detected, decide initial signal position
            position = "BUY"
            if point['ema_12'] > point['ema_26']:
                position = "SELL"
            
            # now check backwards to see if it's part of a trend
            trend_check = self.prices[resolution][index-10:index]
            trend_ok = True
            for p in trend_check:
 
                p_position = "BUY"
                if p['ema_12'] > p['ema_26']:
                    p_position = "SELL"
                if position != p_position:
                    trend_ok = False
                    break
            
            if trend_ok:
                if position=="BUY":
                    confirmation_price = body_top + (big_shadow*size)
                else:
                    confirmation_price = body_bottom - (big_shadow*size)

                comment = "o:{}, c:{}, h:{}, l:{}".format(open_price,close_price,high_price,low_price)
                self.add_signal(resolution,point['snapshotTime'],position,"HAMMER",comment,round(confirmation_price,2))

    def add_signal(self,resolution, snapshot_time, position, signal_type, comment = "", confirmation_price = None ):
        """Add a signal to the market"""
        matching_signals = [x for x in self.signals if (x.snapshot_time == snapshot_time and x.type==signal_type)]
        # remove any previous crossover signals - new one superceeds them
        if signal_type=="CROSSOVER":
            for signal in matching_signals:
                self.signals.remove(signal)
            matching_signals = []

        if len(matching_signals)==0:
            self.signals.append(Signal(self.epic,resolution,snapshot_time,position,signal_type, comment, confirmation_price))

    # ********* Indicator calculations ***********
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
            
    def calculate_trailing(self, resolution):
        # highs = np.asarray([x['highPrice']['bid'] for x in self.prices[resolution][-40]]).reshape((5,-1)).amax(axis=1)
        # lows = np.asarray([x['lowPrice']['ask'] for x in self.prices[resolution][-40]]).reshape((5,-1)).amin(axis=1)
        try:
            highs = [x["highPrice"]['bid'] + self.spread for x in self.prices[resolution]]
            # print(highs)
            self.exponential_average(resolution,12,highs,"high_trail")
            self.exponential_average(resolution,12,[x["lowPrice"]['bid'] - self.spread for x in self.prices[resolution]],"low_trail")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno,exc_obj)
            pass
        

    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i + n]

    def calculate_rsi(self, resolution, n=14):
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

        future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=mins)

        prediction_point = future_time - epoch.replace(tzinfo=datetime.timezone.utc)


        prediction = (m * prediction_point.total_seconds()) + c


        return prediction, m, c

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
