#!/usr/bin/python

DOCUMENTATION = '''
---
module: set_power_state 
short_description: set dell power state 
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
  state:
    description:
      - choices: On/ForceOff/GracefulRestart/GracefulShutdown/PushPowerButton
    required: true
'''

EXAMPLES = '''

- set_power_state:
    idrac: "192.168.1.1"
    username: "root"
    password: "admin1234"
    state: GracefulRestart 
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
            state=dict(required=True),
        ),
        supports_check_mode=False
    )
    idrac_ip = module.params['idrac']
    idrac_username = module.params["username"]
    idrac_password = module.params["password"]
    state = module.params["state"]

    url = 'https://%s/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset' % idrac_ip
    headers = {'content-type': 'application/json'}
    payload = {'ResetType': state}
    response = requests.post(url, data=json.dumps(payload), headers=headers, verify=False, auth=(idrac_username,idrac_password))
    statusCode = response.status_code
    if statusCode != 204:
        module.fail_json(msg="Setting power failed with error code %s, details: %s" % (statusCode, str(response.__dict__)))
    else:
        module.exit_json(changed=True, result="success")

if __name__ == '__main__':
    main()
