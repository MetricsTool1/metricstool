#!/usr/bin/env python3
import time
from datetime import datetime as dt
import sys
import os
import re
import datetime
import argparse
import pathlib
import gzip
import logging
import json
import traceback


LOGGERNAME = 'MetricsTool'
logging.basicConfig(format='%(asctime)s - %(name)s - %(module)s:%(lineno)d- %(levelname)s - %(message)s', datefmt="%Y-%m-%dT%H:%M:%S%z")
logger = logging.getLogger(LOGGERNAME)

plot_extension = '.html'
plot_prefix = 'metricsplot-'
default_background = 'black'

Background = ['black','blue','beige','grey','red']
default_background_index = 1
dot_colours = ['blue', 'orange', 'white', 'red', 'purple']
default_dot_colours_index = 2

default_timestamp_format= 'monthname'
timestamp_format_options = {'american':'%-m/%-d', 'european':'%-d/%-m',default_timestamp_format: '%-d/%-m'}

Timestamp_key = 'Timestamp'
Timestamp_Group_Name = Timestamp_key
MetricsName_Group_Name = 'MetricsName'
MetricsValue_Group_Name = 'MetricsValue'
MetricsUnit_Group_Name = 'MetricsUnit' # what is metricsunit?
Timestamp_Regex = r'^(?P<' + Timestamp_Group_Name + r'>\[?\d\d\d\d-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d\d\d)?[A-Z]?)\]?'# what is (? for

def getTemplate() :
    template_fname = 'templategit.html'# Plot template
    self = pathlib.Path(__file__)
    directory = self.parent
    template = directory/template_fname
    if template.exists():
      print('Template = ', template)
    else:
      print('Template not found')
    return template



def getArgs():
  """
    get the cli arguments
  """
  parser = argparse.ArgumentParser(
      description='MyExample',
      formatter_class=argparse.ArgumentDefaultsHelpFormatter
  )
  parser.add_argument('-D', '--debug', action='store_true',
                      required=False, default=False,
                      help='Set the debug level to DEBUG')
  parser.add_argument('-P', '--prefix', action='store',
                      required=False, default=plot_prefix,
                      help='Prefix to add to the input file name to produce the output file name')
  parser.add_argument('-S', '--suffix', action='store',
                      required=False, default=plot_extension,
                      help='Suffix to add to the input file name to produce the output file name')
  parser.add_argument('-H', '--height', action='store', type=int,
                      required=False, default=350,
                      help='Height of each figure, in pixels')
  parser.add_argument('-W', '--width', action='store', type=int,
                      required=False, default=1200,
                      help='Width of each figure, in pixels')
  parser.add_argument('files', action='store', nargs='+',
                      help='file(s) to parse')
  parser.add_argument('-B', '--background', action='store', required=False, choices=Background,
                      default=default_background, help='Choose your chart background')
  parser.add_argument('-C', '--dotcolour', action='store', required=False, choices=dot_colours,
                      default=dot_colours[default_dot_colours_index],
                      help='Choose your dot colour')

  # Argument for storage option??
  parser.add_argument('-o', '--outputdir', action='store', type=pathlib.Path, required=False,
                      help='Provide a directory if you want the output to be stored separately')

  parser.add_argument('-L', '--formattimestamp', action='store',required=False, choices=timestamp_format_options.keys(), default= default_timestamp_format, help ='Choose your timestamp format')
  metricsG = parser.add_mutually_exclusive_group(required=True)
  metricsG.add_argument('-l', '--list', action='store_true', required=False,
                        help='List all the metrics detected in the supplied file(s)')
  metricsG.add_argument('-m', '--metrics', action='append', required=False,
                        help='Name of metric to be plotted, can be repeated multiple times')
  parser.add_argument('-r', '--regexes', action='store', type=pathlib.Path,
                      help='file containing additional regexes.')
  parser.epilog = 'The format of the regex file is one regex per line, without the timestamp part (will be added automatically). Each new regex needs to contain at least the following groups: ' + ','.join([MetricsName_Group_Name, MetricsValue_Group_Name]) + ' and this optional group: ' + MetricsUnit_Group_Name

  return parser.parse_args()



def convert_timestamp(ts):
  return datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%f%z')



regexes = [
    re.compile(Timestamp_Regex + r' .+logging-metrics-publisher LoggingMeterRegistry \d+ (?P<' + MetricsName_Group_Name + r'>[^ ]+) .*value=(?P<' + MetricsValue_Group_Name +r'>[0-9.]+)(?: (?P<' + MetricsUnit_Group_Name + r'>[^ ]+))?'),
    re.compile(Timestamp_Regex + r' .+logging-metrics-publisher LoggingMeterRegistry \d+ (?P<' + MetricsName_Group_Name + r'>[^ ]+) .*mean=(?P<' + MetricsValue_Group_Name +r'>[0-9.]+)(?P<' + MetricsUnit_Group_Name + r'>[^ ]+)'),
]

def regex_extract(line, regex):
  """
    check if regex matches line, and if it does,
    return the dictionaries with the key/values describing the groups in the regex
  """
  m = regex.match(line)
  if m is None:
    return None
  return dict(m.groupdict().items())

def zopen(fname):
  """
    Wrapper around open and gzip.open.
    If the file is gzipped, it will be opened with gzip,
    otherwise, it will be opened with open
    returns a file object as if it were opened with open(fname, 'r')
  """
  #Try to open the file and catch BadGzipFile
  with gzip.open(fname, 'rt') as tempfile:
    try:
      _ = tempfile.read(2)
    except gzip.BadGzipFile:
      return open(fname,'rt', encoding='utf-8')
  return gzip.open(fname, 'rt', encoding='utf-8')


def prettifyMetricName(metric):
  """
    Clear unwanted stuff from a metric/counter name
  """
  if metric.endswith('{}'):
    return metric[:-2]
  return metric

def parse(logfile, stopWhenLoopDetected=False):
  """
    Read logfile line by line, match each line against a list of regexes,
    and extract the data by timestamp.
    While parsing, keep a list of counters identified, and for each, keep track of their units
    Returns a tuple containg: (results, counters)
    where results is a dictionary indexed by timestamps, pointing to a dictionary indexed by metric name, where the value is the collected value
    and counters is a dictionary indexed by metric name, and the value is the unit used for such metric
    if stopWhenLoopDetected is True, scanning the file will stop as soon as a metric repeated in the file being parsed.
    This is useful for listing counters from a file
  """
  results = dict()
  counters = dict()
  fullsize = os.path.getsize(logfile)
  with zopen(logfile) as f:
    for line in f:
      line = line.rstrip('\n')
      for regex in regexes:
        record = regex_extract(line, regex)
        if record:
          if Timestamp_Group_Name in record:
            # Copy over all the values except Timestamp, which should be used as the key of the dictionary instead
            #First ensure that the metric has a name:
            if record.get(MetricsName_Group_Name):
              #Then prettify its name
              record[MetricsName_Group_Name] = prettifyMetricName(record.get(MetricsName_Group_Name))
              #Then add the timestamp if it doesn't exist:
              if record[Timestamp_Group_Name] not in results:
                results[record[Timestamp_Group_Name]] = dict()
                #Then copy the value over
              results[record[Timestamp_Group_Name]][record[MetricsName_Group_Name]] = record.get(MetricsValue_Group_Name, 0)
              #{k: v for k, v in record.items() if k not in (Timestamp_Group_Name, MetricsName_Group_Name)}
              #Lastly, update the list of counters
              if record[MetricsName_Group_Name] not in counters:
                counters[record[MetricsName_Group_Name]] = record.get(MetricsUnit_Group_Name,'') or ''
              elif stopWhenLoopDetected:
                logger.debug('Stopping processing file %s because counter %s has just been repeated', logfile, record[MetricsName_Group_Name])
                return results, counters
            else:
              logger.debug('Line %s in file %s has no metric name, ignored', line, logfile)
          else:
            logger.debug('Line %s in file %s has no timestamp, ignored', line, logfile)
          # As soon as one of the regex matches, we stop
          break
    if hasattr(f.buffer, 'fileobj'):
      currentpos = f.buffer.fileobj.tell()
    else:
      currentpos = f.tell()
    logger.info('Progress: reading %s is %.02f%%', logfile, 100*currentpos/fullsize)
  return results, counters

 # create a new plot


def parse_and_plot(logfile, plotfile, args):
  results, counters = parse(logfile, stopWhenLoopDetected=False)
  #We need to keep a map of desired counters pointing back to their order
  #This makes it easier to select the correct list in data
  selectedcounters = {m:i for i,m in enumerate(args.metrics)}

  #Allocate data to contain a list for each selected metric
  data = [list() for _ in range(len(args.metrics))]

  for timestamp,datapoints in results.items():
    for counter,value in datapoints.items():
      #Select the correct list using the counter to index mapping. If the counter is not a selected one, this will return None
      dataindex = selectedcounters.get(counter)
      #If the counter is selected, and the dataindex is not None, add the value to the corresponding list
      if dataindex is not None:
        timestamp = convert_timestamp(timestamp)
        timestamp = str(timestamp).split('.', 1)[0]
        data[dataindex].append({'date':timestamp, 'value':value})
    
  placeholders = {
      '@WIDTH@': json.dumps(args.width),
      '@HEIGHT@': json.dumps(args.height),
      '@BACKGROUNDCOLOUR@': args.background,
      '@DOTCOLOUR@': args.dotcolour,
      '@TIMESTAMP@': args.formattimestamp,
      '@DATASET@': json.dumps(data, indent=4, sort_keys=True, default=str)
  }

  # update placeholders in template
  templatefname = getTemplate()
  try:
    source_file = open(templatefname, 'r', encoding='utf-8')
  except Exception as e:
    logger.error('Error opening the template file %s: %s', templatefname, e)
  else:
    try:
      plot_file = open(plotfile, 'w', encoding='utf-8')
    except Exception as e:
      logger.error('Error opening the output file %s: %s', plotfile, e)
    else:
      with source_file, plot_file:
        for line in source_file.readlines():#load line by line in memory??
          for placeholder, value in placeholders.items():
            if placeholder in line:
              line = line.replace(placeholder, value)
          plot_file.write(line)

def loadRegexes(regexes_filename):
  """
    Given a filename containing regexes
    load them into the list if they compile
    ignore them if they fail to compile
    ignore non-existing file or Null
  """
  if regexes_filename:
    try:
      regexfile = open(regexes_filename, 'rt', encoding='utf-8')
    except Exception as e:
      logger.error('Supplied regex file %s filed to open: %s, will be ignored ', regexes_filename, e)
    else:
      with regexfile:
        for line in regexfile:
          if not line.startswith('#'):
            candidate_regex = Timestamp_Regex + line.rstrip('\n')
            try:
              compiled_regex = re.compile(candidate_regex)
            except Exception as e:
              logger.warning('Regex %s from supplied file %s failed to compile: %s. It will be ignored', candidate_regex, regexes_filename, e)
            else:
              #We need to ensure that all the required groups are supplied
              Proceed = True
              for g in (Timestamp_Group_Name, MetricsName_Group_Name, MetricsValue_Group_Name):
                if g not in compiled_regex.groupindex:
                  logger.error('Regex %s from supplied file %s lacks group %s and will be ignored', candidate_regex, regexes_filename, g)
                  Proceed = False
                  break
              if Proceed:
                logger.debug('Appending regex %s to the list', candidate_regex)
                regexes.append(compiled_regex)

if __name__ == "__main__":
  args = getArgs()
  if args.debug:
    logging.getLogger().setLevel(logging.DEBUG)
  else:
    logging.getLogger().setLevel(logging.INFO)
  loadRegexes(args.regexes)

  for fname in args.files:
        logFile = "LogFile_" + str(fname) + ".log"
        with open(logFile, 'w') as logfile:
            try:
                if ".gz" in str(fname) or ".txt" in str(fname):
                    logger.info('Processing input file %s', fname)
                    logfile.write('Processing input file:' + fname + '\n')
                    logfname = pathlib.Path(os.path.normpath(fname))
                    if args.list:
                        _, counters = parse(logfname, stopWhenLoopDetected=True)
                        sys.stdout.write(f'List of counters detected in input file {fname}\n')
                        for counter in counters:
                            sys.stdout.write(f'{counter}\n')
                        sys.stdout.write('\n')
                    else:
                        plotfname = logfname.parent / "{0}{1}{2}".format(args.prefix, logfname.name, args.suffix)
                        try:
                            parse_and_plot(logfname, plotfname, args)
                        except FileNotFoundError:
                            logger.error('File not found: %s', fname)
                            logfile.write('File not found:' + fname + '\n')
                            continue

                        logger.info('Processed file %s. Plot results stored in %s', logfname, plotfname)
                        logfile.write('Processed file:' + str(logfname) + " " + 'Plot results stored in:' + str(plotfname) + '\n')
                else:
                    logger.error('Unsupported File Type: %s', fname)
                    logfile.write('Unsupported File Type:' + fname + '\n')
            except Exception as e:
                    logger.error(traceback.format_exc())
                    logfile.write('Error:' + traceback.format_exc())
