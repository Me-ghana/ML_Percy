import os
import json
import pandas as pd 


pd.set_option('display.max_columns',None)

with open('Rover Waypoints.json') as json_file:
	data = json.load(json_file)

df = pd.json_normalize(data, record_path = "features")
#print(df.head(3))

df = df.rename(columns={"properties.sol":"sol", "properties.lat":"lat", "properties.lon":"lon"})
#print(df["sol"])
print(df.query('sol == 501')["lat"])
#res = df.set_index("properties.sol").T.to_dict('list')
#print(res[501])

# properties.sol
# properties.lon
# properties.lat
print('hi')
print(os.listdir())