import json
a = []
for i in range(10):
    name = "id_{}".format(i)
    obj = {
        "name": name,
        "val" : i,
        "thing": True
    }
    a.append(obj)

del a[5]['thing']
print(a)
b = [x for x in a if "thing" not in x]
print(b)

fh = open("markets/prices/CS.D.AUDUSD.TODAY.IP.json")
c = json.load(fh)

d = [x['snapshotTime'] for x in c['prices']['MINUTE_5'] if "mfi_14" not in x]
print(d)