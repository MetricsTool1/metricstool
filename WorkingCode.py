import re
import argparse
from datetime import datetime
import pathlib
import os


parser = argparse.ArgumentParser()
parser.add_argument('filename', nargs='+', type=pathlib.Path, help='name of the file to open')
option1 = 0
option2 = 1

parser.add_argument('-a', '--average', action='store_true', required=False,
                    help='print the average instead of all the values')

parser.add_argument('-o', '--outputdir', action='store', type=pathlib.Path, required=False,
                    help='it will specify same directory as output')
args = parser.parse_args()

date = 'timestamp'
number = 'number'

# ^ stand for start

re1 = re.compile(r'^(?P<' + date + r'>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}[\d]{1,2}\s\d{2}:\d{2}:\d{2}).*\[(?P<' + number + r'>[0-9]+)\]')

re2 = re.compile(r'^(?P<' + date + r'>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s{1,2}[\d]{1,2}\s\d{2}-\d{2}-\d{2}).*\[(?P<' + number + r'>[0-9]+)\]')
regexes = (re1,re2)

# open the file and read each line
# file = args.filename
for file in args.filename:
    # one dic for one file
    data_dict = {}
    with open(file, 'r') as f:
        for line in f:
            for regex in regexes:
                match = regex.search(line)
                if match:
                    timestamp_str = match.group(date)
                    number_str = match.group(number)
                    # change year from 1900 to 2023
                    # One line only for try
                    # Further modification is possible with line below
                    if "-" in timestamp_str:
                        timestamp = datetime.strptime(timestamp_str, '%b %d %H-%M-%S').replace(year=datetime.now().year)
                    else:
                        timestamp = datetime.strptime(timestamp_str, '%b %d %H:%M:%S').replace(year=datetime.now().year)
                    if timestamp not in data_dict:
                        data_dict[timestamp] = []
                    data_dict[timestamp].append(int(number_str))
                    break

    #wd = str(os.getcwd())
    #filenameinstrformat = str(file)
    #filename = filenameinstrformat[:-4] + '.out'
    #f_output = open(os.path.join(wd, filename), 'wt', encoding='utf-8')

    outputdir = file.parent
    if args.outputdir is not None:
        outputdir = args.outputdir
    f_output = open(outputdir/(file.stem + '.out'), 'wt', encoding='utf-8')

    with f_output:
        if args.average:
            for key in data_dict:
                value = data_dict[key]
                avg = sum(value) / len(value)
                # print(f'{key}={avg}')
                print('{key}={avg}'.format(key=key, avg=avg))
                f_output.write('{key}={avg}'.format(key=key, avg=avg))
                f_output.write('\n')
        else:
                print(data_dict)
