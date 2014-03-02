#!/usr/bin/env python
import collections
import inspect
import json
import urllib
import urllib2
import sys

OK = 0
WARNING = 1
CRITICAL = 2
UNKNOWN = 3

def latest(points):
  return points[-1][0]

class Checks(object):

  def __init__(self):
    self._results = None
    self._active_events = set()

  def run(self):
    self._results = []
    # TODO(bluecmd): threading pool?
    self.access_ifSpeed('15min', 'min')
    self.access_uplinkTraffic('15min')

    # Clear events that are not firing anymore
    current_events = set()
    for target, check, _, _ in self._results:
      event = (target, check)
      current_events.add(event)

    non_firing = self._active_events - current_events
    for target, check in non_firing:
      self._results.append((target, check, OK, 'Metric returned to normal'))

    print 'Current events: ', current_events
    print 'Events that stopped: ', non_firing

    self._active_events = current_events
    return self._results

  def _get(self, time, *targets):
    query = {}
    query['format'] = 'json'
    query['from'] = '-%s' % time
    query['until'] = '-1min'
    aliased_targets = ["aliasSub(%s,'^.*dh\.(.*?)\.1.*$','%s|\\1')" % (
      target, target_id) for target_id, target in targets]

    url = 'http://localhost:8011/render/?%s&%s' % (
        urllib.urlencode(query),
        '&'.join([urllib.urlencode({'target': target}) for target in aliased_targets]))
    data = urllib2.urlopen(url)
    retdict = collections.defaultdict(dict)
    for target in json.loads(data.read()):
      target_id, target_name = target['target'].split('|', 1)
      retdict[target_id][target_name] = target['datapoints']
    return [retdict[target_id] for target_id, _ in targets]

  def _targetToDns(self, target):
    return '.'.join(reversed(target.split('.')))

  def _warning(self, target, message):
    check = inspect.stack()[1][3]
    self._results.append((self._targetToDns(target), check, WARNING, message))

  def _critical(self, target, message):
    check = inspect.stack()[1][3]
    self._results.append((self._targetToDns(target), check, CRITICAL, message))

  def access_ifSpeed(self, time, method):
    # ifHighSpeed
    oid = '1.3.6.1.2.1.31.1.1.1.15.*'
    link_speed_query = ('link-speed',
      "summarize(dh.local.dreamhack.event.*.%s,'%s','%s',true)" % (
        oid, time, method))

    (link_speed, ) = self._get(time, link_speed_query)

    if method == 'avg' or method == 'min':
      for target, data in link_speed.iteritems():
        if latest(data) != 1000:
          self._warning(target, 'Uplink slower than 1 Gbps, is %d Mbps' % (
            latest(data),))

  def access_uplinkTraffic(self, time):
    # ifHcInOctets
    in_oid  = '1.3.6.1.2.1.31.1.1.1.6.*'
    # ifHcOutOctets
    out_oid = '1.3.6.1.2.1.31.1.1.1.10.*'

    in_query = ('in-trafic',
      "summarize(scale(dh.local.dreamhack.event.*.%s,0.033),'%s','avg',true)" % (
        in_oid, time))

    out_query = ('out-trafic',
      "summarize(scale(dh.local.dreamhack.event.*.%s,0.033),'%s','avg',true)" % (
        out_oid, time))

    (traffic_in, traffic_out) = self._get(time, in_query, out_query)

    for target, data in traffic_in.iteritems():
      # traffic is in Mbits/s
      traffic = latest(data) / 10**6 * 8
      if traffic > 900:
        self._critical(target, 'Traffic level on uplink extreme, is %d Mbits/s' % (
          traffic,))
      elif traffic > 700:
        self._warning(target, 'Traffic level on uplink high, is %d Mbits/s' % (
          traffic,))

if __name__ == '__main__':
  c = Checks()
  c._results = []
  if len(sys.argv) == 1:
    print c.run()
  else:
    getattr(c, sys.argv[1])(*sys.argv[2:])
    print c._results

