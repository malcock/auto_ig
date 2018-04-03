import numpy as np

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

