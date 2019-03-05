#!/usr/bin/python

DOCUMENTATION = '''
---
module: drac_set_boot_order
short_description: set dell boot order 
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
  boot_devices:
    description:
      - list of boot devices 
    required: true
  retries:
    description:
      - retry times in case url request fails
    required: false
'''

EXAMPLES = '''

- drac_set_boot_order:
    idrac: "192.168.1.1"
    username: "root"
    password: "admin1234"
    boot_devices: 
      - Index: 0
        Enabled: true
        Id: BIOS.Setup.1-1#BootSeq#NIC.Integrated.1-3-1#b2401d51f8600b7a76c243bea93fbc17
        Name: NIC.Integrated.1-3-1
      - Index: 1
        Enabled: true
        Id: BIOS.Setup.1-1#BootSeq#HardDisk.List.1-1#c9203080df84781e2ca3d512883dee6f
        Name: Optical.SATAEmbedded.J-1 
'''

RETURN = '''
# Default return values
'''
ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


import warnings
from drac_utils import bios

from ansible.module_utils.basic import AnsibleModule

warnings.filterwarnings("ignore")


def main():
    module = AnsibleModule(
        argument_spec=dict(
            idrac=dict(required=True),
            username=dict(required=True),
            password=dict(required=True, no_log=True),
            boot_devices=dict(required=True),
            retries=dict(required=False, default=3)
        ),
        supports_check_mode=False
    )

    idrac = bios(module, "update_boot_order")
    idrac.update_boot_order()


if __name__ == '__main__':
    main()

