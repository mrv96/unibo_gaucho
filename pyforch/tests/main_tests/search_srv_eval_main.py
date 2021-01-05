from __future__ import annotations
import os
import sys
from typing import Any, List

from pyshark.capture.capture import StopCapture
sys.path.append("/home/gaucho/mario/unibo_gaucho/pyforch")
# print(sys.path)
# print(sys.modules)

from src.forch.fo_service import Service
from src.forch.fo_slp import SLPFactory
from src.forch.fo_servicecache import ServiceCache

import pyshark

from pathlib import Path
import argparse
import asyncio
from ipaddress import IPv4Address
import time # https://stackoverflow.com/questions/5849800/what-is-the-python-equivalent-of-matlabs-tic-and-toc-functions
import netifaces as ni

from collections import deque
import threading
import csv

class TicToc:
  def __init__(self, name:str|None=None, print_out:bool=True):
    self.__name: str|None = name
    self.__tstart : float
    self.__elapsed: float = -1
    self.__print_out: bool = print_out

  def get_elapsed(self):
    return self.__elapsed

  def tic(self):
    self.__tstart = time.time()
    return self.__tstart

  def toc(self, print_out:bool|None=None):
    self.__elapsed = time.time() - self.__tstart
    if print_out is None:
      print_out = self.__print_out
    if print_out:
      if self.__name:
        print('[{}] '.format(self.__name), end='')
      print('Elapsed: {}'.format(self.__elapsed))
    return self.__elapsed

  def __enter__(self):
    self.tic()

  def __exit__(self, type, value, traceback):
    self.toc(print_out=True)


class Sniffer(threading.Thread):
  def __init__(self, ifaces:List[str], timeout:int|None=None, out_file:str|bool=False):
    super().__init__()
    self.__timeout = timeout
    self.__stop: bool = False
    self.__ifaces: List[str] = ifaces
    self.__pkts: List[Any] = [] # list of packets
    self.__out_file: str|bool = out_file
    self.__cap: pyshark.LiveCapture

  def get_packets_list(self):
    return self.__pkts # Is it better to use threading.Lock() and perform a deepcopy?

  def stop(self):
    self.__stop = True

  def __load_packets(self, packet_count=0, timeout=None):
    def keep_packet(pkt):
      self.__pkts.append(pkt)
      if self.__stop == True:
        raise StopCapture()

    try:
      self.__cap.apply_on_packets(keep_packet, timeout=timeout, packet_count=packet_count)
    except:
      pass

  def run(self):
    self.__stop = False
    self.__pkts = []
    if isinstance(self.__out_file, str):
      self.__cap = pyshark.LiveCapture(interface=self.__ifaces, output_file=self.__out_file)#, bpf_filter='port 427||port 1847||multicast', display_filter='srvloc')
    elif self.__out_file:
      self.__cap = pyshark.LiveCapture(interface=self.__ifaces, output_file="tst.pcap")#, bpf_filter='port 427||port 1847||multicast', display_filter='srvloc')
    else:
      self.__cap = pyshark.LiveCapture(interface=self.__ifaces)#, bpf_filter='port 427||port 1847||multicast', display_filter='srvloc')
    self.__load_packets(timeout=self.__timeout)



if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Test FORCH OpenSLP implementation.')
  # Optional arguments
  parser.add_argument('-m', '--mode', choices=['c', 'd'], default='d', help='Specify SLP working mode: c (centralized) or d (distributed).')
  parser.add_argument('-i', '--ifaces', nargs="+", help='Specify the inet ifaces where run SLP.')
  parser.add_argument('-a', '--ipaddrs', nargs="+", help='Specify the ip addresses where run SLP.')
  parser.add_argument('-j', '--files', nargs="+", default=['../service_example.json'], help='Specify the service JSON files to be used.')
  parser.add_argument('-t', '--times', type=int, default=1, help='Specify the number of trials to be done')
  # Mandatory arguments
  parser.add_argument('dev', choices=['o', 'n'], help='Specify the device type: o (for orchestrator) or n (for node).')
  # requiredNamed = parser.add_argument_group('required named arguments')
  # parser.add_argument('-d', '--dev', choices=['o', 'n'], required=True, help='Specify the device type: o (for orchestrator) or n (for node).')
  args = parser.parse_args()

  # This script must be run as root!
  if not os.geteuid()==0:
    sys.exit('This script must be run as root!')

  iface_list = []
  ip_list = []
  if args.ifaces is not None:
    iface_list = args.ifaces
  if args.ipaddrs is not None:
    ip_list = [IPv4Address(ip) for ip in args.ipaddrs]
  if not iface_list and not ip_list:
    iface_list = ni.interfaces()

  #ipv4 = ni.ifaddresses('lo')[ni.AF_INET][0]['addr']
  for iface in iface_list:
   for ip in ni.ifaddresses(str(iface))[ni.AF_INET]:
     ip_list.append(ip['addr'])

  ip_list = list(set(ip_list))

  # parse json files
  srv_list = []
  for json in args.files:
    for ip in ip_list:
      srv_list.extend(Service.create_services_from_json(json_file_name=str(Path(__file__).parent.joinpath(json).absolute()), ipv4=ip))
  srv_list = Service.aggregate_nodes_of_equal_services(srv_list)

  if args.dev == 'n':
    # Sniffer not required because we sniff on the only DA/UA of the network
    sa = SLPFactory.create_SA()
    for srv in srv_list:
      sa.register_service(srv)
    asyncio.get_running_loop().run_forever()
  else:
    all_res = [['TRIAL TYPE: {}+{}'.format(args.dev, args.mode), 'TIME', 'N_PKTS', 'TOT_BYTES', 'DATA_CONSISTENCY']]
    da = None

    for i in range(args.times):
      fnd: List[Service] = []
      elapsed_time: float = -1
      n_pkts: int = -1
      tot_bytes: int = 0

      if args.mode == 'd':
        monitor = Sniffer(ifaces=iface_list, timeout=5, out_file=('test{}.pcap'.format(i)))
        tt = TicToc("Test SC Refresh #{}".format(i))

        monitor.start() # TODO: mettere uno sleep di sicurezza dopo questa istruction?
        sc = ServiceCache()

        tt.tic()
        sc.refresh()
        elapsed_time = tt.toc()

        monitor.stop()
        monitor.join()
        pkts_list = monitor.get_packets_list()

        fnd = sc.get_list()
      else:
        monitor = Sniffer(ifaces=iface_list, timeout=5, out_file=('test{}.pcap'.format(i)))
        monitor.start() # TODO: mettere uno sleep di sicurezza dopo questa istruction? Metterlo qua o dopo il DA in modo da avere timeout più corti?
        if da is None:
          da = SLPFactory.create_DA(new_handler=True)
          input('DA started. Press enter to find services...')

        ua = SLPFactory.create_UA()
        tt = TicToc("Test UA Find Srvs #{}".format(i))
        tt.tic()
        fnd = ua.find_all_services()
        elapsed_time = tt.toc()

        monitor.stop()
        monitor.join()
        pkts_list = monitor.get_packets_list()

      n_pkts = len(pkts_list)
      for pkt in pkts_list:
        tot_bytes += pkt.length
      print('Number of received packets: {}'.format(n_pkts))
      print('Total packets length [bytes]: {}'.format(tot_bytes))

      passed = str(all([el for i, el in enumerate([ann.__dict__ == fnd[fnd.index(ann)].__dict__ for ann in srv_list]) if i != 2]))
      
      all_res.append([str(i), str(elapsed_time), str(n_pkts), str(tot_bytes), str(passed)])
      # assert all([el for i, el in enumerate([ann.__dict__ == fnd[fnd.index(ann)].__dict__ for ann in srv_list]) if i != 2]), "Some found service is different from the registered one"

    with open('res.csv', mode='w') as res_file:
      res_writer = csv.writer(res_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
      res_writer.writerows(all_res)
