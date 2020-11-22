import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.absolute()))

from forch.forch_utils_service import Service
from forch.forch_utils_slp import SLPFactory
from ipaddress import IPv4Address

import asyncio

def test_counter_methods_effectiveness():
  number_of_agents = 5
  agents_list = []

  for i in range(1, number_of_agents+1, 1):
     agents_list.append(SLPFactory.create_UA())
     assert SLPFactory._SLPFactory__common_agents_counter == i, ""

  for i in range(number_of_agents-1, -1, -1):
    agents_list.pop(i)
    assert SLPFactory._SLPFactory__common_agents_counter == i, ""

  SLPFactory.create_UA(True)
  assert SLPFactory._SLPFactory__common_agents_counter == 0, ""

def test_SA_and_UA():
  # SA MAIN
  sa = SLPFactory.create_SA()
  srv_list = Service.create_services_from_json(IPv4Address("127.0.0.1"), str(Path(__file__).parent.joinpath("service_example.json").absolute()))
  for srv in srv_list:
    sa.register_service(srv)

  #UA MAIN
  ua = SLPFactory.create_UA()
  fnd = ua.find_all_services()
  assert all([ann.__dict__ == fnd[fnd.index(ann)].__dict__ for ann in srv_list]), ""

  # Run this to catch eventual exceptions
  for srv in fnd:
    sa.deregister_service(srv)

# Test DA agent
# if __name__ == "__main__":
#   da = SLPFactory.create_DA()
#   asyncio.get_event_loop().run_forever()