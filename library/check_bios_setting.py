#!/usr/bin/python

DOCUMENTATION = '''
---
module: check_bios_setting 
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
'''

EXAMPLES = '''

- set_bios_attr:
    idrac: "192.168.1.1"
    username: "root"
    password: "admin1234"
    key_value_pairs:
      LogicalProc: Enabled
      SriovGlobalEnable: Enabled
      ProcVirtualization: Enabled 
    values: Enabled 
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
            key_value_pairs=dict(required=True)
        ),
        supports_check_mode=False
    )
    idrac_ip = module.params['idrac']
    idrac_username = module.params["username"]
    idrac_password = module.params["password"]
    key_value_pairs = json.loads(re.sub(r'\'', '"', module.params["key_value_pairs"]))

    tries = 3
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

    mismatched = {}
    data = response.json()
    for key in key_value_pairs:
        if key_value_pairs[key] != data['Attributes'][key]:
            mismatched[key] = data['Attributes'][key]
    if len(mismatched) > 0:
        module.exit_json(changed=False, result="failed", msg="BIOS setting mismatch: %s" %json.dumps(mismatched))
    else:
        module.exit_json(changed=False, result="success", msg="BIOS setting matched")


if __name__ == '__main__':
    main()
