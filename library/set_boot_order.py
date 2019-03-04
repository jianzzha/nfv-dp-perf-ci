#!/usr/bin/python

DOCUMENTATION = '''
---
module: set_boot_order
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

- set_boot_order:
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
            boot_devices=dict(required=True),
            retries=dict(required=False, default=3)
        ),
        supports_check_mode=False
    )
    idrac_ip = module.params['idrac']
    idrac_username = module.params["username"]
    idrac_password = module.params["password"]
    boot_devices_str = module.params["boot_devices"]
    #first convert ' to " per json spec
    boot_devices_str = re.sub(r'\'', '"', boot_devices_str)
    # next convert True to true, False to false per json spec
    boot_devices_str = re.sub(r'True', 'true', boot_devices_str)
    boot_devices_str = re.sub(r'False', 'false', boot_devices_str)
    boot_devices = json.loads(boot_devices_str)
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
    current_boot_mode = data[u'Attributes']["BootMode"]

    for round in range(tries):
        try:
            response = requests.get('https://%s/redfish/v1/Systems/System.Embedded.1/BootSources' % idrac_ip,verify=False,auth=(idrac_username, idrac_password))
        except requests.exceptions.SSLError:
            continue
        else:
            break

    data = response.json()
    if data[u'Attributes'] == {}:
        module.fail_json(msg="no %s boot order devices detected for iDRAC IP %s" % (current_boot_mode,idrac_ip)) 

    if current_boot_mode == "Uefi":
        boot_seq = "UefiBootSeq"
    else:
        boot_seq = "BootSeq"

    current_boot_devices = data[u'Attributes'][boot_seq]
    # update the boot order only if required is different than current boot order
    if any(x !=y for x, y in zip(current_boot_devices, boot_devices)):
        pass
    else:
        # if current boot order list is equal to required, do nothing
        module.exit_json(changed=False, msg="nothing to change")

    url = 'https://%s/redfish/v1/Systems/System.Embedded.1/BootSources/Settings' % idrac_ip
    payload = {'Attributes': {boot_seq:boot_devices}}
    headers = {'content-type': 'application/json'}
    for round in range(tries):
        try:
            response = requests.patch(url, data=json.dumps(payload), headers=headers, verify=False,auth=(idrac_username, idrac_password))
        except requests.exceptions.SSLError:
            continue
        else:
            break
    statusCode = response.status_code
    if statusCode != 200:
        module.fail_json(msg="Failed to change boot device error code %s, details: %s" % (statusCode, str(response.__dict__)))

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

