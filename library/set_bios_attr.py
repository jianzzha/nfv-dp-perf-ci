#!/usr/bin/python

DOCUMENTATION = '''
---
module: set_bios_attr
short_description: set dell bios attributes
options:
  idrac:
    description:
      - server iDrac address 
    required: true
  username:
    description:
      - User name for a user with admin rights
    required: true 
  password:
    description:
      - Password for the given 'username'
    required: true
  key_value_pairs:
    description:
      - dict of key:value pairs 
    required: true
  retries:
    description:
      - retry times in case url request fails
    required: false
'''

EXAMPLES = '''

- set_bios_attr:
    idrac: "192.168.1.1"
    username: "root"
    password: "admin1234"
    key_value_pairs:
      LogicalProc: Enabled
      PowerSaver: Disabled
      ProcVirtualization: Enabled
      SriovGlobalEnable: Enabled
'''

RETURN = '''
# Default return values
'''
ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


import requests, json, sys, re, time, warnings
from datetime import datetime

from ansible.module_utils.basic import AnsibleModule

warnings.filterwarnings("ignore")


def main():
    module = AnsibleModule(
        argument_spec=dict(
            idrac=dict(required=True),
            username=dict(required=True),
            password=dict(required=True, no_log=True),
            key_value_pairs=dict(required=True),
            retries=dict(required=False, default=3)
        ),
        supports_check_mode=False
    )
    idrac_ip = module.params['idrac']
    idrac_username = module.params["username"]
    idrac_password = module.params["password"]
    key_value_pairs_str = module.params["key_value_pairs"]
    key_value_pairs_str = re.sub(r'\'', '"', key_value_pairs_str)
    key_value_pairs_str = re.sub(r'True', 'true', key_value_pairs_str)
    key_value_pairs_str = re.sub(r'False', 'false', key_value_pairs_str)
    key_value_pairs = json.loads(key_value_pairs_str)
    tries = int(module.params["retries"])
 
    for round in range(tries):
        try:
            response = requests.get('https://%s/redfish/v1/Systems/System.Embedded.1/Bios' % idrac_ip, verify=False, auth=(idrac_username, idrac_password))
        except requests.exceptions.SSLError:
            # not sure the reason behind this exception, 
            # but rerun might just work
            continue
        else:
            break

    if response.status_code != 200:
        module.fail_json(msg="Incompatible iDRAC version")

    data = response.json()
    payload = {"Attributes":{}}
    for key in key_value_pairs:
        # only update the setting if current value is different
        if data['Attributes'][key] != key_value_pairs[key]:
            payload["Attributes"][key] = key_value_pairs[key] 
    
    #if nothing to update, skip
    if len(payload["Attributes"]) == 0:
        module.exit_json(changed=False, msg="nothing to change")

    url = 'https://%s/redfish/v1/Systems/System.Embedded.1/Bios/Settings' % idrac_ip
    headers = {'content-type': 'application/json'}
    for round in range(tries):
        try:
            response = requests.patch(url, data=json.dumps(payload), headers=headers, verify=False, auth=(idrac_username, idrac_password))
        except requests.exceptions.SSLError:
            continue
        else:
            break

    statusCode = response.status_code
    if statusCode != 200:
        module.fail_json(msg="BIOS setting failed with error code %s, details: %s" % (statusCode, str(response.__dict__)))

    url = 'https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs' % idrac_ip
    payload = {"TargetSettingsURI":"/redfish/v1/Systems/System.Embedded.1/Bios/Settings"}
    headers = {'content-type': 'application/json'}
    for round in range(tries):
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers, verify=False,auth=(idrac_username, idrac_password))
        except requests.exceptions.SSLError:
            continue
        else:
            break

    statusCode = response.status_code
    if statusCode != 200:
        module.fail_json(msg="Create BIOS setting Job failed with error code %s" % statusCode)    
    d=str(response.__dict__)
    z=re.search("JID_.+?,",d).group()
    job_id=re.sub("[,']","",z)

    while True:
        try:
            req = requests.get('https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs/%s' % (idrac_ip, job_id), auth=(idrac_username, idrac_password), verify=False)
        except requests.exceptions.SSLError:
            continue
        statusCode = req.status_code
        data = req.json()
        if statusCode != 200:
            module.fail_json(msg="check job status failed with code %s, detail: %s" %(statusCode, data))
        if data[u'Message'] == "Task successfully scheduled.":
            module.exit_json(changed=True, result="success", msg="reboot required to complete") 
        else:
            time.sleep(10) 


if __name__ == '__main__':
    main()
    


