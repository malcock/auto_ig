import numpy as np

def crossover_hold(series_1, series_2, lookback=3):
    now = series_1[-1] - series_2[-1]
    orig =  series_1[-lookback] - series_2[-lookback]
    if now >0 and orig<0:
        # first test passed now check periods between
        for i in range(2,lookback):
            now=  series_1[-i] - series_2[-i]
            if now < 0:
                return False
        return True
    return False

def crossunder_hold(series_1, series_2, lookback=3):
    now = series_1[-1] - series_2[-1]
    orig =  series_1[-lookback] - series_2[-lookback]
    if now <0 and orig>0:
        # first test passed now check periods between
        for i in range(2,lookback):
            now = series_1[-i] - series_2[-i]
            if now > 0:
                return False
        return True
    return False


def find_crossover(series,value=0):
    # try to find a crossover in the supplied series
    
    place = -1
    if len(series)<2:
        raise ValueError("series is too short - must be 2 or greater")

    if isinstance(value,(list,np.ndarray)):
        if len(value) < len(series):
            raise ValueError("if using list as value, it must be equal or greater length than series")
        
       
        for i in range(2,len(series)):
            if crossover(series[:i],value[:i]):
                place = i
                break
        

    else:
        for i in range(2,len(series)):
            if crossover(series[:i],value):
                place = i
                break
    return place

def find_crossunder(series,value=0):
    # try to find a crossover in the supplied series
    
    place = -1
    if len(series)<2:
        raise ValueError("series is too short - must be 2 or greater")

    if isinstance(value,(list,np.ndarray)):
        if len(value) < len(series):
            raise ValueError("if using list as value, it must be equal or greater length than series")
        
       
        for i in range(2,len(series)):
            if crossunder(series[:i],value[:i]):
                place = i
                break
        

    else:
        for i in range(2,len(series)):
            if crossunder(series[:i],value):
                place = i
                break
    return place

def crossover(series, value=0):
    """series = the series we want to compare
        value or list that the series must cross over
    """
    now = series[-1]
    prev = series[-2]
    
    if isinstance(value,(list,np.ndarray)):
        if now > value[-1] and prev < value[-2]:
            return True
    else:
        if now > value and prev < value:
            return True
    
    return False

def crossunder(series, value=0):
    """series = the series we want to compare
        value or list that the series must cross under
    """
    now = series[-1]
    prev = series[-2]
    if isinstance(value,(list,np.ndarray)):
        if now < value[-1] and prev > value[-2]:
            return True
    else:
        if now < value and prev > value:
            return True
    
    return False

def isabove(value,*args):
    """returns true if given value is above all the supplied args"""
    for arg in args:
        if value < arg:
            return False

    return True

def isbelow(value,*args):
    for arg in args:
        if value > arg:
            return False
    
    return True

def candleover(series, prices):
    now = prices[-1]
    prev = prices[-2]

    if ((now['closePrice']['bid'] > series[-1] and now['openPrice']['bid'] > series[-1])
        and (prev['closePrice']['bid'] < series[-2] or prev['openPrice']['bid'] < series[-2])):
        return True
    
    return False

def candleunder(series, prices):
    now = prices[-1]
    prev = prices[-2]
    if ((now['closePrice']['bid'] < series[-1] and now['openPrice']['bid'] < series[-1]) 
        and (prev['closePrice']['bid'] > series[-2] or prev['openPrice']['bid'] > series[-2])):
        return True

    
    return False

