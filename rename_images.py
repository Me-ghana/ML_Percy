import webgeocalc
import os
import re

directory = 'M2020_Street_View_Images_May14/'

for filename in os.listdir(directory):
	
	img_name = filename
	img_name = img_name[:-4]
	if (img_name[-3:]=='UTC'):
		continue

	res = re.findall('(\d{10})',filename)
	if (res):
		sclk_time = res[0]
		dic = webgeocalc.TimeConversion(kernels=19, times = sclk_time, time_system='SPACECRAFT_CLOCK', time_format='SPACECRAFT_CLOCK_STRING', sclk_id=-168, verbose=False).run()
		utc = dic.get('DATE2')
		print(utc)

		source = directory + filename
		dest = directory + img_name + '_' + utc + '.png'
		os.rename(source,dest)
    
