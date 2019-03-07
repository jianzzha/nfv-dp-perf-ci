#!/usr/bin/python

DOCUMENTATION = '''
---
module: drac_set_bios_attr
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

- drac_set_bios_attr:
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

import warnings, sys, os
from ansible.module_utils.basic import AnsibleModule

try:
    from ansible.module_utils.drac_utils import bios
except ImportError:
    # if drac_utils not importable via ansible, see if python can find it
    util_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir, "module_utils")
    sys.path.append(util_path)
    from drac_utils import bios 

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

    # /redfish/v1 may change in the future with newer redfish version
    idrac = bios(module, "/redfish/v1", "update_bios")
    idrac.update_bios()
     

if __name__ == '__main__':
    main()
    


