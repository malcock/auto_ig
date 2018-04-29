import logging
import time
import datetime
import math
import json
import operator
import sys
import requests
from functools import reduce
from pytz import timezone

import os

from Cryptodome.Cipher import AES

from .lightstreamer import LSClient, Subscription
from .market import Market
from .trade import Trade
from .strategy import *


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


class AutoIG:
    """Handles authentication and coordination of IG"""

    def __init__(self):
        self.authenticated_headers = {}
        self.markets = {}
        self.trades = []
        self.max_concurrent_trades = 6
        self.lightstream = {}
        self.key = ""
        self.is_open = True
        self.strategy = {}
        # self.strategy['wma_cross'] = wma_cross(10,25,50,14)
        self.strategy['stoch'] = stoch(14,3,3)
        # self.strategy['obv_psar'] = obv_psar(14,7)
        # self.strategy['mfi'] = mfi(9,9,40)

    def make_trade(self, size, market, prediction, json_data = None):
        """Make a new trade"""
        logger.info("making a trade")
        t = Trade(size, market,prediction, json_data)
        self.trades.append(t)
        return t


    def fill_signals(self):
        for m in self.markets.values():
            print('backfilling {}'.format(m.epic))
            for s in m.strategies.values():
                s.backfill(m,'MINUTE_30')

    def get_signals(self):
        
        signals = {}
        for k,s in self.strategy.items():
            signals[k] = sorted(s.signals, key=operator.attrgetter('timestamp'),reverse=True)
        
        return signals


    def process(self,epic_ids):
        """Do the process"""
        timenow = datetime.datetime.now()

        # if timenow.weekday() == 5:
        #     return False, "We don't play on weekends"

        # if timenow.weekday() == 4:
        #     if timenow.time() > datetime.time(21):
        #         # close for the weekend
        #         if self.is_open:
        #             if isinstance(self.lightstream, LSClient):
        #                 self.lightstream.unsubscribe_all()
                    
        #             self.lightstream = {}

        #             for m in self.markets.values():
        #                 m.prices = {}
        #                 m.save_prices()

        #             self.is_open = False
        #         return False, "Markets closed on Friday"

        # if timenow.weekday() ==6:
        #     if timenow.time() > datetime.time(21):
        #         if not self.is_open:
        #             self.is_open = True
        #     else:
        #         return False, "Market still closed on Sunday"


        self.update_markets(epic_ids)


        # first - are there any saved trades?
        try:
            path = "trades/open"
            trades_on_file = [name for name in os.listdir(path) if name.endswith(".json")]
            logger.info("number of trades found: {}, trades in memory: {}".format(len(trades_on_file),len(self.trades)))
            if len(self.trades)<len(trades_on_file):
                logger.info("trades on file disparity")
                for name in trades_on_file:
                    fh = open(os.path.join(path,name),"r")
                    json_trade = json.load(fh)
                    logger.info("loaded file: " + name)
                    if json_trade['market'] in self.markets:
                        self.make_trade(1,self.markets[json_trade['market']],json_trade['prediction'],json_trade)
            elif len(self.trades)>len(trades_on_file):
                # try to clean up trades list
                logger.info("trying to clean up trades list")
                set_trades = {}
                for t in self.trades:
                    set_trades[t.deal_id] = t

                self.trades  = list(set_trades.values())
                            

        except Exception as e:
            logger.error(e)
        
        open_lightstreamer = False
        
        for m in self.markets.values():
            # if state has changed force an update to the lightstream obj
            if m.market_status!=m.last_status:
                open_lightstreamer = True

            if m.market_status == "TRADEABLE":
                if m.get_update_cost("DAY",30)>0:
                    m.update_prices("DAY",30)

                if m.get_update_cost("MINUTE_30",60)>0:
                    m.update_prices("MINUTE_30",60)

                if m.get_update_cost("MINUTE_5",60)>0:
                    m.update_prices("MINUTE_5",60)
            
        

        # let's process our markets and look for signals then
        top_markets = sorted(self.markets.values(), key=operator.attrgetter('spread'))
        for market in top_markets:
            self.insta_trade(market)
            
            
        if not isinstance(self.lightstream, LSClient):
            open_lightstreamer = True

        # either no lightstreamer object was found, or the epics have changed
        if open_lightstreamer:
            epic_list = [x.epic for x in self.markets.values() if x.market_status=="TRADEABLE"]
            # epic_list = self.markets.keys()
            if len(epic_list)==0:
                return False, "No epics to open lightstream with, weird huh"
            if isinstance(self.lightstream, LSClient):
                self.lightstream.unsubscribe_all()
            else:
                try:
                    headers = self.authenticate()
                    password = "CST-" + str(headers['CST']) + "|XST-" + str(headers['X-SECURITY-TOKEN'])
                    logger.info(self.lightstreamerEndpoint)
                    logger.info(self.api_user)
                    logger.info(password)
                    self.lightstream = LSClient(self.lightstreamerEndpoint,"",self.api_user,password)
                    logger.info("attempting to connect to lightstream")

                    self.lightstream.connect()
                    logger.info("connect?")
                except Exception as e:
                    logger.info("Unable to connect to Lightstreamer Server - clearing headers")
                    logger.info(e)
                    self.authenticated_headers = {}
                    self.lightstream = {}
                    self.lightstreamerEndpoint = ""

                    return False, "Failed to open lighstreamer: {}".format(e)

            # assuming here that we've got a lighstream connection so we can subscribe now
            
            epic_ids_time = ["CHART:" + s + ":5MINUTE" for s in epic_list]
            logger.info(epic_ids_time)
            live_charts = Subscription(mode="MERGE", items=epic_ids_time, fields="LTV,UTM,DAY_HIGH,DAY_LOW,OFR_OPEN,OFR_HIGH,OFR_LOW,OFR_CLOSE,BID_OPEN,BID_HIGH,BID_LOW,BID_CLOSE,CONS_END,CONS_TICK_COUNT".split(","),adapter="DEFAULT")
            live_charts.addlistener(self.live_update)
            self.live_charts_key = self.lightstream.subscribe(live_charts)



        return True, "hello"

    def insta_trade(self,market):
        for strategy in market.strategies.values():
            
            signals = [x for x in strategy.signals if x.score>1 and x.unused and x.market==market.epic]
            for signal in signals:
                current_trades = [x for x in self.trades if x.market==market]
                if len(current_trades)==0:
                    if signal.score > 2:
                        if market.spread < 4:
                            if len(self.trades)<self.max_concurrent_trades:
                                round_val = 500.0
                                base = 1000.0
                                trade_size = max(0.5,(round_val*math.floor((float(self.account['balance']['balance'])/round_val))-500)/base)
                                logger.info("proposed bet size: {}".format(trade_size))

                                signal.unused = False
                                prediction = strategy.prediction(signal,market,'MINUTE_30')
                                self.make_trade(1,market,prediction)
                                signal.score = 1
                            else:
                                logger.info("Can't open any more trades already maxed out")
                        else:
                            logger.info("{} : market spread too wide!".format(market.epic))
                else:
                    logger.info("{} trade already open on this market".format(market.epic))
                    for t in current_trades:
                        if signal.position == t.prediction['direction_to_trade']:
                            t.log_status("{} signal reenforced {} - {} - {}".format(market.epic,signal.position, signal.name, signal.timestamp))
                            signal.unused = False
                            signal.score-=1
                        else:
                            
                            # t.assess_close(signal)
                            strategy.assess_close(signal,t)
                            
                            signal.score-=1
                            if signal.score > 2:
                                signal.unused = True

    def live_update(self,data):
        # get the epic
        epic = data['name'].split(":")[1]
        if epic in self.markets:
            self.markets[epic].set_latest_price(data['values'])
            market_trades = [x for x in self.trades if x.market.epic==epic]
            
            for t in market_trades:
                if not t.update():
                    self.trades.remove(t)


    def update_markets(self, epic_ids):
        logger.info("getting all markets data")
        for chunk in list(self.chunks(epic_ids,50)):

            base_url = self.api_url + '/markets?epics=' + ','.join(chunk)
            auth_r = requests.get(base_url, headers=self.authenticate())
            if auth_r.ok:
                res = json.loads(auth_r.text)
                epics_data = res["marketDetails"]
                for epic in epics_data:
                    epic_id = epic['instrument']['epic']
                    if not epic_id in self.markets:
                        m = Market(epic_id,self,epic)
                        for s in self.strategy.values():
                            m.add_strategy(s)
                        self.markets[epic_id] = m 
                        
                    else:
                        self.markets[epic_id].update_market(epic)
            else:
                return False, "Couldn't get market data: {} {}".format(auth_r.status_code,auth_r.content)

    def backtest(self, epic, start_date, end_date):
        """do a backtest - probs should have done this a while ago..."""
        pass


    def get_history(self):
        base_url = self.api_url + "/history/transactions/ALL/100000000000000"
        
        auth_r = requests.get(base_url, headers=self.authenticate())

        history = json.loads(auth_r.text)


        return history['transactions']
            
    def chunks(self, l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i + n]


    def initialise(self, is_live, settings):
        self.settings = settings.copy()
        if is_live:
            self.api_url = 'https://api.ig.com/gateway/deal'
            self.api_key = settings['api_key']
            self.api_user = settings['api_user']
            self.api_pass = settings['api_pass']
        else:
            self.api_url = 'https://demo-api.ig.com/gateway/deal'
            self.api_key = settings['demo_api_key']
            self.api_user = settings['demo_api_user']
            self.api_pass = settings['demo_api_pass']

        logger.info(self.api_url)
        logger.info(self.api_key)
        logger.info(self.api_user)
        logger.info(self.api_pass)

    def login(self):
        """login to IG"""
        base_url = self.api_url + "/accounts"
        try:
            logger.info("logging in...")
            auth_r = requests.get(base_url, headers=self.authenticate())
            d = json.loads(auth_r.text)

            for i in d['accounts']:
                if str(i['accountType']) == "SPREADBET":
                    logger.info ("Spreadbet Account ID is : " + str(i['accountId']))
                    spreadbet_acc_id = str(i['accountId'])
                    self.account = i

            base_url = self.api_url + "/session"
            data = {"accountId":spreadbet_acc_id,"defaultAccount": "True"}
            logger.info("making sure right account selected...")
            auth_r = requests.put(base_url, data=json.dumps(data), headers=self.authenticate())


            return True
        except Exception as err:
            logger.info("login failed - check credentials")
            logger.info(err)
            return False

    def authenticate(self):
        """Authenticate with IG"""
        if 'CST' in self.authenticated_headers:
            return self.authenticated_headers
        else:
            logger.info("generating new headers")
            data = {"identifier":self.api_user, "password":self.api_pass}
            headers = {'Content-Type':'application/json; charset=utf-8',
                'Accept':'application/json; charset=utf-8',
                'X-IG-API-KEY':self.api_key,
                'Version':'2'}
            
            base_url = self.api_url + "/session"
            # logger.info(base_url)
            # rep = requests.get(REAL_OR_NO_REAL + "/session",data=json.dumps(data),headers=headers)

            rep = requests.post(base_url,data=json.dumps(data), headers=headers)

            if rep.status_code == 200:

                self.account = json.loads(rep.text)
                logger.info(self.account)
                self.lightstreamerEndpoint = self.account['lightstreamerEndpoint']
                headers_json = dict(rep.headers)

                headers =  {'Content-Type':'application/json; charset=utf-8',
                            'Accept':'application/json; charset=utf-8',
                            'X-IG-API-KEY':self.api_key,
                            'CST':headers_json["CST"],
                            'X-SECURITY-TOKEN':headers_json["X-SECURITY-TOKEN"]}
                
                self.authenticated_headers = headers

                return self.authenticated_headers
            else:
                logger.info("auth failed: " + str(rep.status_code) + " " + rep.reason)



    ##################################################
    ############# FILE SAVE / ENCRYPTION #############
    ##################################################
    def save_file(self, data, filename, is_bytes=False):
        """Save a file"""
        mode = "wb" if is_bytes else "w"
        f = open(filename, mode)
        f.write(data)
        f.close()

    def read_file(self, filename, is_bytes=False):
        """Read a file"""
        mode = "rb" if is_bytes else "r"
        f = open(filename, mode)
        data = f.read()
        f.close()
        return data

    def save_json(self, json_data, filename, encrypted=False):
        """Saves dict to a file as json, optionally with encryption"""
        save_data = json.dumps(json_data)
        logger.info(save_data)
        is_bytes = False
        if encrypted:
            cipher = AES.new(self.key, AES.MODE_EAX)
            ciphertext, tag = cipher.encrypt_and_digest(save_data.encode('utf8'))
            file_out = open(filename, "wb")
            [ file_out.write(x) for x in (cipher.nonce, tag, ciphertext) ]
            is_bytes = True
        else:
            self.save_file(save_data, filename, is_bytes)

    def load_json(self, filename, encrypted=False):
        """Load json from a file into a dict optionally with decryption"""
        try:
            json_str = self.read_file(filename, encrypted)
            if encrypted:
                file_in = open(filename, "rb")
                nonce, tag, ciphertext = [ file_in.read(x) for x in (16, 16, -1) ]

                # let's assume that the key is somehow available again
                cipher = AES.new(self.key, AES.MODE_EAX, nonce)
                json_str = cipher.decrypt_and_verify(ciphertext, tag)
                # json_str = decrypt( self.KEY, json_str)
            return json.loads(json_str)
        except IOError:
            
            # no file found, but just return None - let calling code handle that
            return None

    
