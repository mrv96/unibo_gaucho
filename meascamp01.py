import time
import requests
import json
import datetime

#curl -X DELETE http://127.0.0.1:5003/nodes
print("DELETE", "http://127.0.0.1:5003/nodes")
r = requests.delete("http://127.0.0.1:5003/nodes")
print("Sleep for 240 seconds")
time.sleep(240)

#curl http://192.168.10.117:5001/apps
print("GET", "http://192.168.10.117:5001/nodes")
r = requests.get("http://192.168.10.117:5001/apps")
time.sleep(1)

# request the allocation of new service
print("GET", "http://192.168.10.117:5001/app/FA002")
r = requests.get("http://192.168.10.117:5001/app/FA002")
resp_json = r.json()
print(json.dumps(resp_json, indent=2))
time.sleep(1)

while r.status_code in [200, 201]:
  # gather data on deployed service
  node_ip = resp_json["node_ip"]
  serv_port = resp_json["service_port"]

  # start new service
  url = "http://{}:{}/app/FA002".format(node_ip, serv_port)
  data_json = {"timeout":10000, "cpu":1}
  print("POST", data_json, url)
  r = requests.post(url, json=data_json)
  resp_json = r.json()
  print(json.dumps(resp_json, indent=2))
  time.sleep(1)

  print("Sleep for 120 seconds")
  time.sleep(120)

  # request the allocation of new service
  print("GET", "http://192.168.10.117:5001/app/FA002")
  r = requests.get("http://192.168.10.117:5001/app/FA002")
  resp_json = r.json()
  print(json.dumps(resp_json, indent=2))
  time.sleep(1)

print("Sleep for 240 seconds")
time.sleep(240)

# get measurements
print("GET", "http://127.0.0.1:5003/meas")
r = requests.get("http://127.0.0.1:5003/meas")
time.sleep(1)
with open("../gauchotest/get_meas_test_{0:%Y%m%d_%H%M%S}.json".format(datetime.datetime.now()), "w") as f:
  json.dump(r.json(), f)

#curl -X DELETE http://127.0.0.1:5003/nodes
print("DELETE", "http://127.0.0.1:5003/nodes")
r = requests.delete("http://127.0.0.1:5003/nodes")
time.sleep(1)

