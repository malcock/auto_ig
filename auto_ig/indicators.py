import operator
import numpy as np

def atr(window, prices, name = None):
    if name is None:
        name = "atr_{}".format(window)

    previous_day = prices[0]
    prev_close = float(previous_day['closePrice']['mid'])

    tr_prices = []

    for p in prices[1:]:
        high_price = float(p['highPrice']['mid'])
        low_price = float(p['lowPrice']['mid'])
        price_range = high_price - low_price

        tr = max(price_range, abs(high_price-prev_close), abs(low_price-prev_close))
        tr_prices.append(tr)

        prev_close = p['closePrice']['mid']



    atr = np.mean(rolling_window(np.asarray(tr_prices),window),axis=1)
    diff = len(prices) - atr.size
    
    for i in range(diff,len(prices)):
        prices[i][name] = atr[i-diff]

    return atr,tr_prices

def net_change(prices):
    for p in prices:
        p['net_change'] = p['closePrice']['mid'] - p['openPrice']['mid']

def ema(window, prices = None, name = None, values= None):
    def numpy_ewma_vectorized_v2(data, window):

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


    if values is None:
        if prices is None:
            raise Exception("values or prices or both must be supplied")
        values = np.asarray([x['closePrice']['mid'] for x in prices])
    else:
        values = np.asarray(values)

    a = numpy_ewma_vectorized_v2(values,window)

    if prices is not None:
        if name is None:
            name = "ema_{}".format(window)
        
        price_len = len(prices)
        diff = price_len - len(a)
        
        for i in range(diff,price_len):
            prices[i][name] = a[i-diff]
    return a

def ma(window, prices = None, values = None, name = None):
    """Simple moving average
        price data, window"""
    if values is None:
        if prices is None:
            raise Exception("values or prices or both must be supplied")
        values = np.asarray([x['closePrice']['mid'] for x in prices])
    else:
        values = np.asarray(values)

    a = np.mean(rolling_window(values,window),axis=1)
    if prices is not None:
        if name is None:
            name = "ma_{}".format(window)

        price_len = len(prices)
        diff = price_len - len(a)
        
        for i in range(diff,price_len):
            prices[i][name] = a[i-diff]
    
    return a

def macd(prices,fast=12,slow=26,signal=9):
    fast_ema = ema(fast, prices = prices)
    slow_ema = ema(slow, prices = prices)
    macd = np.subtract(fast_ema,slow_ema)
    sig = ema(signal,prices,"macd_signal",macd)
    histo = np.subtract(macd,sig)
    for i in range(0,len(prices)):
        prices[i]['macd'] = macd[i]
        prices[i]['macd_histogram'] = histo[i]

def mfi(prices,length=14):

    volumes = np.asarray([x['lastTradedVolume'] for x in prices])
    
    tp = np.asarray([x['typicalPrice']['mid'] for x in prices])

    diff = np.diff(tp)
    len_diff = len(prices) - len(diff)

    for i in range(len_diff,len(prices)):
        prices[i]['diff'] = diff[i-len_diff]

    upper = []
    lower = []
    for i in range(1,len(tp)):
        if tp[i-1] < tp[i]:
            u = volumes[i] * tp[i]
            l = 0
        else:
            u = 0
            l = volumes[i] * tp[i]
        
        upper.append(u)
        lower.append(l)
    upper = rolling_sum(upper,length)
    lower = rolling_sum(lower,length)
    ratio = np.array(upper)/np.array(lower)

    mfi = 100. - (100. / (1. + ratio))

    len_diff = len(prices) - len(mfi)

    for i in range(len_diff,len(prices)):
        prices[i]['mfi_{}'.format(length)] = mfi[i-len_diff]


    return mfi


def obv(prices, smooth=10):
    vals = []
    for i in range(1,len(prices)):
        diff = prices[i]['closePrice']['mid'] - prices[i-1]['closePrice']['mid']
        val = 0
        if diff > 0:
            val = prices[i]['lastTradedVolume']
        elif diff < 0:
            val = -prices[i]['lastTradedVolume']
        else:
            val = 0
        vals.append(val)
    
    obv = np.cumsum(np.array(vals))
    signal = wma(10,values=obv)
    obv = obv[len(obv) - len(signal):]
    histo = np.subtract(obv,signal)

    len_diff = len(prices) - len(histo)

    for i in range(len_diff,len(prices)):
        prices[i]['obv_{}'.format(smooth)] = histo[i-len_diff]
    

    return histo


def psar(prices, iaf = 0.02, maxaf = 0.2):
    barsdata = prices
    length = len(barsdata)
    dates = [x['snapshotTime'] for x in barsdata]
    high = [x['highPrice']['mid'] for x in barsdata]
    low = [x['lowPrice']['mid'] for x in barsdata]
    close = [x['closePrice']['mid'] for x in barsdata]
    psar = close[0:len(close)]
    psarbull = [None] * length
    psarbear = [None] * length
    bull = True
    af = iaf
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
            prices[i]['psar_bull'] = psar[i]
            prices[i]['psar_bear'] = ''
        else:
            psarbear[i] = psar[i]
            prices[i]['psar_bear'] = psar[i]
            prices[i]['psar_bull'] = ''

    return {"dates":dates, "high":high, "low":low, "close":close, "psar":psar, "psarbear":psarbear, "psarbull":psarbull}

def roc(window=12,prices = None, values = None, name = None):
    if values is None:
        if prices is None:
            raise Exception("values or prices or both must be supplied")
        values = np.asarray([x['closePrice']['mid'] for x in prices])
    else:
        values = np.asarray(values)
    
    if name is None:
        name = "roc"
    rs = []
    for i in range(window,len(values)):
        r = (values[i] - values[i-window])/values[i-window]
        rs.append(r)
        if prices is not None:
            prices[i][name] = r

    return rs

def rsi(window = 14, prices = None, values = None, name = None):
    """Calculate the RSI"""
    if values is None:
        if prices is None:
            raise Exception("values or prices or both must be supplied")
        values = np.asarray([x['closePrice']['mid'] for x in prices])
    else:
        values = np.asarray(values)
    n = window
    deltas = np.diff(values)
    seed = deltas[:n+1]
    up = seed[seed>=0].sum()/n
    down = -seed[seed<0].sum()/n
    rs = up/down
    rsi = np.zeros_like(values)
    # rsi[:n] = 100. - 100./(1.+rs)
    # rsi[:n] = -1
    
    if name is None:
        name = "rsi_{}".format(window)

    for i in range(n, len(values)):
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
        if prices is not None:
            prices[i][name] = rsi[i]

    return rsi

def rvi(prices, N=10):
    close_price = [x['closePrice']['mid'] for x in prices]
    open_price = [x['openPrice']['mid'] for x in prices]
    high_price = [x['highPrice']['mid'] for x in prices]
    low_price = [x['lowPrice']['mid'] for x in prices]
    close_open = list(map(operator.sub,close_price,open_price))

    high_low = list(map(operator.sub,high_price,low_price))
    
    close_open = swma(close_open)
    
    high_low = swma(high_low)

    close_open = rolling_sum(close_open,N)
    high_low = rolling_sum(high_low,N)
    

    rvi = np.divide(close_open,high_low)
    sig = swma(rvi)
    rvi = rvi[len(rvi) - len(sig):]
    hist = np.subtract(rvi,sig)
    

    price_len = len(prices)
    diff = price_len - len(sig)
    
    for i in range(diff,price_len):
        prices[i]['rvi'] = rvi[i-diff]
        prices[i]['rvi_signal'] = sig[i-diff]
        prices[i]['rvi_histogram'] = hist[i-diff]

def stochastic(prices, length=5, smoothK=3, smoothD = 3):
    """Calculate stochastic indicator for timeframe"""

    def stoch(close,highs,lows):
        high = np.max(highs)
        low = np.min(lows)
        close = close[-1]
        k =((close - low)/(high - low)) * 100
        return k

    highs = rolling_window(np.asarray([x['highPrice']['mid'] for x in prices]),length)
    lows = rolling_window(np.asarray([x['lowPrice']['mid'] for x in prices]),length)
    closes = rolling_window(np.asarray([x['closePrice']['mid'] for x in prices]),length)
    ks = []
    for i in range(0,len(closes)):
        ks.append(stoch(closes[i],highs[i],lows[i]))

    k = ma(smoothK,values = ks)
    d = ma(smoothD,values = k)

    k = k[len(k) - len(d):]

    price_len = len(prices)
    diff = price_len - len(d)
    name = "{}_{}_{}".format(length,smoothK,smoothD)
    for i in range(diff,price_len):
        prices[i]['stoch_k_{}'.format(name)] = k[i-diff]
        prices[i]['stoch_d_{}'.format(name)] = d[i-diff]

    return k,d

def swma(x):
    a = np.asarray(x)
    roll = rolling_window(a,4)
    # print(roll)
    return np.average(roll,axis=1,weights= [1/6, 2/6, 2/6, 1/6])

def tema(window,prices = None, values = None, name = None):
    if values is None:
        if prices is None:
            raise Exception("values or prices or both must be supplied")
        values = np.asarray([x['closePrice']['mid'] for x in prices])
    else:
        values = np.asarray(values)

    ema1 = ema(window, values = values)
    ema2 = ema(window, values = ema1)
    ema3 = ema(window,values = ema2)
    a = np.multiply(np.add(np.subtract(ema1,ema2),ema3),3)
    if prices is not None:
        if name is None:
            name = "tema_{}".format(window)

        price_len = len(prices)
        diff = price_len - len(a)
        
        for i in range(diff,price_len):
            prices[i][name] = a[i-diff]
    
    return a
        

def trend(values):
    """calculate a positive or negative trend from arbitary array of data"""
    length = len(values)
    if length>1:
        last_value = values[0]
        total = 0
        for i in range(1,length):
            total += (values[i] - last_value)
            last_value = values[i]
        
        total/=length

        return total
    
    return 0

def vwma(window,prices):
    closes = np.asarray([x['closePrice']['mid'] for x in prices])
    volume = np.asarray([x['lastTradedVolume'] for x in prices])

    weights = ma(window,values = np.multiply(closes, volume))
    volumes = ma(window,values = volume)

    vwma = np.divide(weights,volumes)

    price_len = len(prices)
    diff = price_len - vwma.size

    name = "vwma_{}".format(window)

    for i in range(diff,price_len):
        prices[i][name] = vwma[i-diff]
        
    return vwma





def wma(window, prices = None, values = None, name = None):
    """Weighted moving averages
        price data, weighted moving average"""
    if values is None:
        if prices is None:
            raise Exception("values or prices or both must be supplied")
        values = np.asarray([x['closePrice']['mid'] for x in prices])
    else:
        values = np.asarray(values)
    
    w = range(1,window+1)
    
    a = np.average(rolling_window(values,window),axis=1,weights=w)
    if prices is not None:
        if name is None:
            name = "wma_{}".format(window)

        price_len = len(prices)
        diff = price_len - len(a)
        
        for i in range(diff,price_len):
            prices[i][name] = a[i-diff]
        

    return a

def rolling_sum(a, n=4) :
    ret = np.cumsum(a, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    return ret[n - 1:]

def rolling_window(a, window):
    shape = a.shape[:-1] + (a.shape[-1] - window + 1, window)
    strides = a.strides + (a.strides[-1],)
    return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)
