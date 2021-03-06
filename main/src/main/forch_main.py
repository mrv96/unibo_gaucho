import logging
from logging.config import fileConfig
from pathlib import Path
fileConfig(str(Path(__file__).parent.joinpath("logging.ini")))
logger = logging.getLogger(__name__)
logger.info(f"Load {__name__} with {logger}")

from time import sleep
import json

from flask import Flask, request, jsonify
from flask_restful import Resource, Api, reqparse, abort

import requests

import forch
forch.set_orchestrator()

logger.debug(f"IS_ORCHESTRATOR: {forch.is_orchestrator()}")


class Source():

  def __init__(self, *, name, base, service, port_list, description=None):
    self.__id = id
    self.__name = name
    self.__base = base
    self.__service = service
    self.__port_list = port_list
    self.__description = description
    
  def get_id(self):
    return self.__id
  def set_id(self, id) :
    self.__id = id

  def get_name(self):
    return self.__name
  def set_name(self, name) :
    self.__name = name

  def get_base(self):
    return self.__base
  def set_base(self, base) :
    self.__base = base

  def get_service(self):
    return self.__service
  def set_service(self, service) :
    self.__service = service

  def get_port_list(self):
    return self.__port_list
  def set_port_list(self, port_list) :
    self.__port_list = port_list

  def get_description(self):
    return self.__description
  def set_description(self, description) :
    self.__description = description


# class ActiveService():

#   def __init__(self, *, service_id, node_id, base_service_id=None):
#     self.__service_id = service_id
#     self.__node_id = node_id
#     self.__base_service_id = base_service_id if base_service_id is not None else service_id

#   def __eq__(self, obj):
#     if isinstance(obj, self.__class__):
#       return ( self.get_service_id() == obj.get_service_id()
#         and self.get_node_id() == obj.get_node_id()
#         and self.get_base_service_id() == obj.get_base_service_id()
#         )
#     return False

#   def get_service_id(self):
#     return self.__service_id
#   def set_service_id(self, service_id) :
#     self.__service_id = service_id

#   def get_node_id(self):
#     return self.__node_id
#   def set_node_id(self, node_id) :
#     self.__node_id = node_id

#   def get_base_service_id(self):
#     return self.__base_service_id
#   def set_base_service_id(self, base_service_id) :
#     self.__base_service_id = base_service_id


class FOB(object):

  __key = object()
  __instance = None

  def __init__(self, *, key=None):
    assert key == self.__class__.__key, "There can only be one {0} object and it can only be accessed with {0}.get_instance()".format(self.__class__.__name__)

    # define list of available sources (SDP codelets and FVE images)
    self.__source_list = []

    # define list of active services - active means allocated or deployed, not just available
    self.__active_service_list = []

  @classmethod
  def get_instance(cls):
    if cls.__instance is None:
      cls.__instance = cls(key=cls.__key)
    return cls.__instance

  @classmethod
  def del_instance(cls):
    if cls.__instance is not None:
      del cls.__instance

  def __get_source_list(self):
    return self.__source_list

  def __set_source_list(self, src_list):
    assert all( isinstance(s, Source) for s in src_list ), "All elements must be Source objects!"
    self.__source_list = src_list

  def load_source_list_from_json(self, json_file_name):

    # TODO check if file name is already absolute and if it exists
    with open(str(Path(__file__).parent.joinpath(json_file_name).absolute())) as f:
      sources_dict = json.load(f)
    
    src_list = [ Source(name=src["name"], base=src["base"], service=src["service"], port_list=src["ports"])
      for src in sources_dict["sources"] ]
    # equivalent to
    # for src in sources_dict["sources"]:
    #   src_list.append( Source(name=src["name"], base=src["base"], service=src["service"], port_list=src["ports"]))

    self.__set_source_list(src_list)

  def __search_source_for_service(self, service_id, *, priority_list=["FVE", "SDP"]):
    """Searches source that implements requested service"""
    for p in priority_list:
      try:
        return next(src for src in self.__get_source_list() if src.get_service() == service_id and p in src.get_base())
      except StopIteration:
        continue
    logger.debug(f"No source found for service {service_id}")
    return None

  def get_active_service_list(self):
    return self.__active_service_list

  def __set_active_service_list(self, active_service_list):
    assert all( isinstance(s, forch.ActiveService) for s in active_service_list ), "All elements must be ActiveService objects!"
    self.__active_service_list = active_service_list

  def update_active_service_list(self, active_service):
    active_service_list = self.get_active_service_list()
    if active_service not in active_service_list:
      active_service_list.append(active_service)
      self.__set_active_service_list(active_service_list)

  def find_active_services(self, *args, **kwargs):
    """Find currently active services on known nodes"""
    service_list = self.get_service_list(*args, **kwargs)
    for s in service_list:
      for sn in s.get_node_list():
        node_ip = sn.get_ip()
        # query node
        # TODO do this through FOVIM
        response = requests.get(f"http://{node_ip}:6001/services")
        resp_json = response.json()
        sn_service_id_list = resp_json["services"]
        for sn_service_id in sn_service_id_list:
          logger.debug(f"Found active service {sn_service_id}")
          self.update_active_service_list(forch.ActiveService(service_id=sn_service_id, node_ip=node_ip))

  @staticmethod
  def get_service_list(*args, **kwargs):
    return FORS.get_instance().get_service_list(*args, **kwargs)

  @staticmethod
  def get_service(*args, **kwargs):
    return FORS.get_instance().get_service(*args, **kwargs)

  def activate_service(self, service_id):
    """Takes service ID and returns an ActiveService object or None."""
    logger.debug(f"Start activating instance of service {service_id}")
    s = FORS.get_instance().get_service(service_id, refresh_sc=True, refresh_meas=True)
    if s is not None:
      # it means that the service is defined in the service cache
      logger.debug(f"Service {s.get_id()} found in cache")
      # need to check which node is best suited to host the service
      sn = s.get_node_by_metric() # by default returns node with minimum CPU utilization
      logger.debug(f"Found node {sn.get_id()} offering {s.get_id()}")
      if sn is not None:
        # TODO check if best node is compliant with constraints (e.g.: if min CPU is lower than threshold for allocation)
        if True: # TODO set meaningful condition
          # if so, trigger the requested allocation through FOVIM
          logger.debug(f"Allocate service {s.get_id()} on node {sn.get_id()}")
          active_s = FOVIM.get_instance().manage_allocation(service_id=s.get_id(), node_ip=sn.get_ip())
          # TODO verify response is an ActiveService with single service node and return it to user --> 200 OK

          # just before returning, update active service list
          self.update_active_service_list(active_s)

          return active_s
        else:
          # here there are no nodes that are free enough to host this service - it might still be deployable
          logger.debug(f"Nodes offering service {s.get_id()} are too busy")
          # TODO handle this case
          pass
      else:
        # here there are no service nodes associated to this service - it might still be deployable
        logger.debug(f"No nodes offering registered service {s.get_id()}")
        # TODO handle this case - but is it even possible to get here? Because services are registered by nodes offering them
        pass
    
    # we get here if the service is not in the service cache or it is but is offered only by busy nodes
    logger.debug(f"Attempt deployment of service {service_id}")
    # check if service is deployable (e.g.: "by deploying an APP on a IaaS node"), starting by looking for a source that offers the requested service
    src = self.__search_source_for_service(service_id)
    # check if there is a source that offers the requested service
    if src is not None:
      logger.debug(f"Found a source for service {service_id}")
      # check if there is a service that provides the required base (SDP/FVE) for the source
      base_service_id = src.get_base()
      base_s = FORS.get_instance().get_service(base_service_id)
      if base_s is not None:
        # here the base service is present in the service cache
        logger.debug(f"Base service {base_s.get_id()} found in cache")
        # check if there is a node that is free enough to host the new allocation
        sn = base_s.get_node_by_metric()
        logger.debug(f"Found node {sn.get_id()} offering {base_s.get_id()}")
        if sn is not None:
          # TODO check if best node is compliant with constraints (e.g.: if min CPU is lower than threshold for allocation)
          if True: # TODO set meaningful condition
            # if so, deploy the source and allocate service on it
            logger.debug(f"Deploy service {service_id} on node {sn.get_id()} on top of base {base_s.get_id()}")
            active_s = FOVIM.get_instance().manage_deployment(service_id=service_id, source=src, node_ip=sn.get_ip())
            # verify response is a service with single service node and return it to user --> 201 Created
            assert isinstance(active_s, forch.ActiveService) and len(active_s.get_node_list()) == 1, ""
            # just before returning, update active service list
            self.update_active_service_list(active_s)
            return active_s
        else:
          # here there are no more resources for new deployments
          logger.debug(f"Nodes offering base service {base_s.get_id()} are too busy")
          # return service with empty node list --> 503 Service Unavailable
          return forch.Service(id=service_id)

    # here unknown service --> 404 Not Found
    logger.debug(f"Unknown service {service_id}")
    return None

  def deactivate_service(self, service_id):
    logger.debug(f"Start deactivating instances of service {service_id}")
    # find relevant entry or entries in active services
    for active_service in self.get_active_service_list():
      if active_service.get_service_id() == service_id:
        # # use base_service_id to get Service object in order to get id of node where service is deployed
        # base_s = self.get_service(active_service.get_base_service_id())
        # sn = base_s.get_node_by_id(active_service.get_node_id())
        sn = active_service.get_node_by_id(active_service.get_node_id())
        # destroy service on node
        FOVIM.get_instance().manage_destruction(service_id=service_id, node_ip=sn.get_ip())

  def deactivate_all_services(self):
    logger.debug(f"Start deactivating all services")
    # find relevant entry or entries in active services
    for active_service in self.get_active_service_list():
      self.deactivate_service(active_service.get_service_id())


class FORS(object):

  __key = object()
  __instance = None

  def __init__(self, *, key=None):
    assert key == self.__class__.__key, "There can only be one {0} object and it can only be accessed with {0}.get_instance()".format(self.__class__.__name__)
    self.__sc = forch.ServiceCache()

  @classmethod
  def get_instance(cls):
    if cls.__instance is None:
      cls.__instance = cls(key=cls.__key)
    return cls.__instance

  @classmethod
  def del_instance(cls):
    if cls.__instance is not None:
      del cls.__instance

  def __get_service_cache(self):
    return self.__sc

  def __refresh_service_cache(self):
    self.__get_service_cache().refresh()

  def get_service_list(self, *, refresh_sc=False, refresh_meas=False):
    logger.debug(f"Get service list from service cache refresh cache {refresh_sc} refresh meas {refresh_meas}")
    if refresh_sc:
      self.__refresh_service_cache()
    service_list = self.__sc.get_list()
    if refresh_meas:
      for s in service_list:
        s.refresh_measurements()
    return service_list

  def get_service(self, service_id, *, refresh_sc=False, refresh_meas=False):
    try:
      s_list = self.get_service_list(refresh_sc=refresh_sc, refresh_meas=refresh_meas)
      return next(s for s in s_list if s.get_id() == service_id)
    except StopIteration:
      logger.debug(f"Service {service_id} not found")
      return None


class FOVIM(object):

  __key = object()
  __instance = None

  def __init__(self, *, key=None):
    assert key == self.__class__.__key, "There can only be one {0} object and it can only be accessed with {0}.get_instance()".format(self.__class__.__name__)
    self.__da = forch.SLPFactory.create_DA()

  @classmethod
  def get_instance(cls):
    if cls.__instance is None:
      cls.__instance = cls(key=cls.__key)
    return cls.__instance

  @classmethod
  def del_instance(cls):
    if cls.__instance is not None:
      del cls.__instance

  @staticmethod
  def manage_allocation(*, service_id, node_ip):
    logger.debug(f"Allocate {service_id} on node {node_ip}")
    # TODO interact with the node and ensure allocation of service (allocation is not deployment)
    # s = FORS.get_instance().get_service(service_id)
    # sn = s.get_node_by_id(node_id)
    active_s = forch.ActiveService(service_id=service_id, node_ip=node_ip)
    return active_s

  @staticmethod
  def manage_deployment(*, service_id, node_ip, source):
    """Manages deployment of service on node based on source. Returns ActiveService or None"""
    logger.debug(f"Deploy {service_id} on node {node_ip} with source {source}")
    
    base_service_id = source.get_base()

    if base_service_id == "FVE001": # TODO avoid hardcoding of ID
      # send deployment request to node
      response = requests.post(f"http://{node_ip}:6001/services/{service_id}",
        json={"base": source.get_base(), "image": source.get_name()}
        )
      response_code = response.status_code
      if response_code == 201:
        response_json = response.json()
        active_s = forch.ActiveService(service_id=service_id, instance_name=response_json["name"])
        src_port_list = source.get_port_list()
        if len(src_port_list) == 0:
          active_s.add_node(ipv4=node_ip)
        elif len(src_port_list) == 1:
          port = src_port_list[0]
          active_s.add_node(ipv4=node_ip, port=int(response_json["port_mappings"][port]))
        else:
          # TODO handle this case: what's better? Add a separate ServiceNode per port of the service, or a single ServiceNode with multiple ports? (in the latter case, probably need to modify ServiceNode)
          raise NotImplementedError
          # for port in src_port_list:
          #   active_s.add_node(ipv4=node_ip, port=int(response_json["port_mappings"][port]))
        return active_s
      else:
        # TODO handle case of wrong or unexpected status code of response
        return None
    else:
      # TODO handle case of unknown base_service_id -- is it even possible?
      pass

  @staticmethod
  def manage_destruction(*, service_id, node_ip):
    logger.debug(f"Destroy {service_id} on node {node_ip}")
    
    response = requests.delete(f"http://{node_ip}:6001/services/{service_id}")
    # TODO avoid returning this directly, but process it and return a single value, maybe the service id
    return response.json(), response.status_code


### API Resources

class Test(Resource):
  def get(self):
    return {
      "message": f"This component ({Path(__file__).name}) is up!",
      "type": "TEST_OK"
    }

class FogServices(Resource):
  def get(self, s_id=""):
    """Gather list of services and format it in a response."""
    # get list of services
    s_list = FOB.get_instance().get_service_list(refresh_sc=True, refresh_meas=True)
    # create list of service IDs
    s_id_list = [ s.get_id() for s in s_list ]
    # check if a service was specified
    if s_id:
      if s_id in s_id_list:
        return {
          "message": f"Requested service {s_id} found.",
          # "type": "FOCO_SERV_OK",
          "services": [ s_id ]
        }, 200
      else:
        return {
          "message": f"Requested service {s_id} not found.",
          # "type": "FOCO_SERV_LIST",
          "services": []
        }, 404
    else:
      return {
        "message": f"Found {len(s_list)} service(s).",
        # "type": "FOCO_SERV_LIST",
        "services": [ s.get_id() for s in s_list ]
      }, 200

  def post(self, s_id):
    """Submit request for allocation of a service."""

    active_s = FOB.get_instance().activate_service(s_id) # returns ActiveService
    
    if active_s is None:
      # service not found
      return {
          "message": f"Requested service {s_id} not found."
          # "type": "FOCO_SERV_POST",
          # "services": []
        }, 404
    
    if isinstance(active_s, forch.ActiveService):
      assert len(active_s.get_node_list()) in [0,1], "Too many ServiceNodes!"
      if len(active_s.get_node_list()) == 0:
        return {
        "message": f"Service {active_s.get_id()} unavailable."
        # "type": "FOCO_SERV_POST"
        }, 503
      elif len(active_s.get_node_list()) == 1:
        # TODO find a way to distinguish 200 from 201 -- maybe check if service_id and base_service_id are the same, meaning allocation (so 200) or otherwise it's deployment (so 201)
        sn = active_s.get_node_by_id(active_s.get_node_id())
        return {
          "message": f"Service {active_s.get_id()} available on node {sn.get_id()}",
          "node_ip": str(sn.get_ip()),
          "node_port": sn.get_port()
          # "type": "FOCO_SERV_POST"
        }, 200
    else:
      # TODO handle case
      pass

  def delete(self, s_id=""):
    """Submit request for deactivation of services."""
    if s_id:
      FOB.get_instance().deactivate_service(s_id)
      # TODO check if operation was successful
      return {
          "message": f"Service {s_id} deactivated",
          # "node_ip": str(sn.get_ip()),
          # "node_port": sn.get_port(),
          # "type": "FOCO_SERV_POST"
        }, 200
    else:
      FOB.get_instance().deactivate_all_services()
      # TODO check if operation was successful
      return {
          "message": f"All services deactivated",
          # "node_ip": str(sn.get_ip()),
          # "node_port": sn.get_port(),
          # "type": "FOCO_SERV_POST"
        }, 200

if __name__ == '__main__':

  ### Command line argument parser

  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument("address", help="This component's IP address", nargs="?", default="127.0.0.1")
  parser.add_argument("port", help="This component's TCP port", type=int, nargs="?", default=6001)
  # parser.add_argument("--db-json", help="Database JSON file, default: rsdb.json", nargs="?", default="rsdb.json")
  # parser.add_argument("--imgmt-address", help="IaaS management endpoint IP address, default: 127.0.0.1", nargs="?", default="127.0.0.1")
  # parser.add_argument("--imgmt-port", help="IaaS management endpoint TCP port, default: 5004", type=int, nargs="?", default=5004)
  # parser.add_argument("-w", "--wait-remote", help="Wait for remote endpoint(s), default: false", action="store_true", default=False)
  # parser.add_argument("--mon-history", help="Number of monitoring elements to keep in memory, default: 300", type=int, nargs="?", default=300)
  # parser.add_argument("--mon-period", help="Monitoring period in seconds, default: 10", type=int, nargs="?", default=10)
  parser.add_argument("-d", "--debug", help="Run in debug mode, default: false", action="store_true", default=False)
  args = parser.parse_args()

  ### instantiate components

  FOB.get_instance()

  FORS.get_instance()

  FOVIM.get_instance()

  ### perform preliminary operations

  FOB.get_instance().load_source_list_from_json(str(Path(__file__).parent.joinpath("sources_catalog.json").absolute()))
  FOB.get_instance().find_active_services(refresh_sc=True)

  ### REST API

  app = Flask(__name__)

  # @app.before_request
  # def before():
  #   logger.debug("marker start {} {}".format(request.method, request.path))
  
  # @app.after_request
  # def after(response):
  #   logger.debug("marker end {} {}".format(request.method, request.path))
  #   return response  

  api = Api(app)
  api.add_resource(Test, '/test')
  api.add_resource(FogServices, '/services', '/services/<s_id>')
  
  try:
    app.run(host=args.address, port=args.port, debug=args.debug)
  except KeyboardInterrupt:
    pass
  finally:
    logger.info("Cleanup after interruption")
    FOB.del_instance()
    FORS.del_instance()
    FOVIM.del_instance()