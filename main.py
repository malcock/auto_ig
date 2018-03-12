"""Main routing handling"""
import logging
import os
import datetime
import platform
import json
import threading
import time
import random
from flask import Flask
from flask import render_template
from flask import request, redirect, flash, session, url_for

from auto_ig import AutoIG


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



login_success = False

settings = {"username":"admin","password":"admin", "api_live":False, 
            "api_user":"****", "api_pass":"****", "api_key":"****", 
            "demo_api_user":"****", "demo_api_pass":"****", "demo_api_key":"****"}

EPIC_IDS = ["CS.D.GBPUSD.TODAY.IP","CS.D.EURUSD.TODAY.IP","CS.D.USDJPY.TODAY.IP","CS.D.GBPAUD.TODAY.IP","CS.D.EURCAD.TODAY.IP"
            "CS.D.AUDUSD.TODAY.IP","CS.D.EURGBP.TODAY.IP","CS.D.EURJPY.TODAY.IP","CS.D.GBPJPY.TODAY.IP","CS.D.CHFJPY.TODAY.IP"
            "CS.D.USDCAD.TODAY.IP", "CS.D.USDCHF.TODAY.IP","CS.D.EURCHF.TODAY.IP" ]
# EPIC_IDS = ["CS.D.BITCOIN.TODAY.IP"]
START_TIME = datetime.datetime.now(datetime.timezone.utc)
LAST_TRADE = START_TIME

auto_ig = AutoIG()

app = Flask(__name__)
app.debug = True
app.jinja_env.add_extension('pyjade.ext.jinja.PyJadeExtension')
app.secret_key = b'A0Zr98j/3yX R~XHH!jmN]LWX/,?RTsd'



@app.before_first_request
def setup():
    auto_ig.key = app.secret_key
    load_settings = auto_ig.load_json("settings.pref", True)
    if load_settings != None:
        globals()["settings"] = load_settings.copy()
        logger.info("settings loaded: user: {} pass: {} api: {}".format(settings["username"], settings["password"], settings["api_user"]))
    else:
        # need to save an encrypted file for future
        auto_ig.save_json(globals()["settings"], "settings.pref", True)
        logger.info("new settings file created")


@app.before_request
def activate_checker():

    if globals()["login_success"] != True:
        auto_ig.initialise(False,globals()["settings"])
        globals()["login_success"] = auto_ig.login()
        if not globals()["login_success"]:
            flash("API Keys not set or wrong","danger")


@app.route("/process")
def process():
    success, response = auto_ig.process(globals()['EPIC_IDS'])
    return "status: {}, response: {}".format(success,response)

@app.route('/')
def index():
    """Load the main index, login to IG etc"""
    # this feels a bit retarded now, but maybe i'll want to concurrently run some on live and demo mode
    # markets = faig.get_markets(globals()['EPIC_IDS'])
    best_markets = ""
    return render_template("home.jade", epic_list = globals()['EPIC_IDS'], account = auto_ig.account, trade = best_markets, start_time = START_TIME, title = platform.python_version())

@app.route("/reset-log")
def reset_log():
    """reset the log file"""
    fh = open("faig_debug.log","w")
    fh.write("")
    fh.close()

    return "log file deleted"

    
@app.route('/signals')
def show_signals():
    """outputs signals into a list or something"""
    signals = auto_ig.get_signals()
    output = "<ul>"
    for signal in signals:
        output += "<li>{} - {}: {}({}) OK:{}, CONFIRM AT:{} UNUSED:{}, score:{}, comment: {}</li>".format(signal.snapshot_time,signal.epic,signal.action, signal.type,signal.confirmed,signal.confirmation_price, signal.unused, signal.score, signal.comment)
    
    output += "</ul>"

    return output


@app.route('/login', methods = ['GET', 'POST'])
def login():
    """Logs the user in or displays login page"""

    if request.method == 'POST':
        logger.info(request.form)
        if (request.form["username"] == settings["username"]
                and request.form["password"] == settings["password"]):
            session["logged_in"] = True
            flash("Login successful",'info')
            return redirect(url_for('index'))
        else:
            flash("Username or Password incorrect",'warning')
            return render_template("login.jade")
    else:
        return render_template("login.jade")

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out','info')
    return redirect(url_for('index'))

@app.route('/prices/<epic>/<res>')
def get_prices(epic,res):

    prices = auto_ig.markets[epic].prices[res]
    output = "timestamp, low, open, close, high, rsi, ema_12, ema_26, macd,macd_signal, macd_histogram, high_trail, low_trail \r\n"
    for p in prices:
        output+="{}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {} \r\n".format(p['snapshotTime'],
                                                        p['lowPrice']['bid'],
                                                        p['openPrice']['bid'],
                                                        p['closePrice']['bid'],
                                                        p['highPrice']['bid'],
                                                        p.get('rsi',0),
                                                        p.get('ema_12',0),
                                                        p.get('ema_26',0),
                                                        p.get('macd',0),
                                                        p.get('macd_signal',0),
                                                        p.get('macd_histogram',0),
                                                        p.get('high_trail',0),
                                                        p.get('low_trail',0))
    
    return output

@app.route('/prices/<epic>/<res>/table')
def get_prices_table(epic,res):

    prices = auto_ig.markets[epic].prices[res]
    output = "<table>"
    output += "<tr><td>timestamp</td> <td>low</td> <td>open</td> <td>close</td> <td>high</td> <td>rsi</td> <td>ema_12</td> <td>ema_26</td> <td>macd</td> <td>signal</td> <td>macd_histogram</td><td>high_trail</td><td>low_trail</td></tr> \r\n"
    for p in prices:
        output+="<tr><td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td> <td>{}</td></tr> \r\n".format(p['snapshotTime'],
                                                        p['lowPrice']['bid'],
                                                        p['openPrice']['bid'],
                                                        p['closePrice']['bid'],
                                                        p['highPrice']['bid'],
                                                        p.get('rsi',0),
                                                        p.get('ema_12',0),
                                                        p.get('ema_26',0),
                                                        p.get('macd',0),
                                                        p.get('macd_signal',0),
                                                        p.get('macd_histogram',0),
                                                        p.get('high_trail',0),
                                                        p.get('low_trail',0))
    output +="</table>"
    return output

@app.route('/clear-prices')
def clear_prices():
    for m in auto_ig.markets.values():
        m.prices = {}
        m.save_prices()
    
    return "Price data cleared"

@app.route('/settings', methods = ['GET', 'POST'])
def settings_screen():
    """Show the settings screen"""
    if request.method == 'POST':
        # do some settings setting
        logger.info("request: " + str(request.form))
        logger.info("settings: " + str(settings))
        # update password?
        if(request.form["password"] != ""):
            if(request.form["password"] == request.form["password_confirm"]):
                settings["password"] = request.form["password"]
        
        # update simple settings
        update_settings(request.form.copy(), "username",
                        "api_user", "api_pass", "api_key",
                        "demo_api_user", "demo_api_pass", "demo_api_key")
        
        # switch to live mode?
        # print(request.form["api_live"])
        settings["api_live"] = "api_live" in request.form

        logger.info("settings: " + str(settings))
        # rebuild the settings save file
        auto_ig.key = app.secret_key
        auto_ig.save_json(settings, "settings.pref", True)
        logger.info("new settings file created")
        auto_ig.authenticated_headers = {}
        flash("Settings updated", 'info')
        return render_template( "settings.jade", settings = settings)
    else:
        return render_template( "settings.jade", settings = settings)

def update_settings(new_settings, *args):
    """Takes an object and sticks values in based on args keys"""
    for a in args:
        settings[a] = new_settings[a]



if __name__ == '__main__':
    logger.info("running app")

    
    app.run(threaded=True)
