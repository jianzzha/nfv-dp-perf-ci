import requests, json, re, time
from datetime import datetime
from ansible.module_utils.basic import AnsibleModule


class drac_base(object):
    def __init__(self, addr, username, password, retries):
        self.idrac_ip = addr
        self.idrac_username = username
        self.idrac_password = password
        self.retries = retries


    def _patch(self, url, payload, headers):
        for round in range(self.retries):
            try:
                response = requests.patch(url, data=json.dumps(payload), headers=headers, verify=False, auth=(self.idrac_username, self.idrac_password))
            except requests.exceptions.SSLError:
                continue
            except requests.exceptions.ConnectionError:
                # there might be some other polling activity blocking this
                time.sleep(5)
                continue 
            else:
                break
        return response


    def _post(self, url, payload, headers):
        for round in range(self.retries):
            try:
                response = requests.post(url, data=json.dumps(payload), headers=headers, verify=False, auth=((self.idrac_username, self.idrac_password)))
            except requests.exceptions.SSLError:
                continue
            except requests.exceptions.ConnectionError:
                # there might be some other polling activity blocking this
                time.sleep(5)
                continue
            else:
                break
        return response


    def _get(self, url):
        for round in range(self.retries):
            try:
                response = requests.get(url, verify=False, auth=(self.idrac_username, self.idrac_password))
            except requests.exceptions.SSLError:
                continue
            except requests.exceptions.ConnectionError:
                # there might be some other polling activity blocking this
                time.sleep(5)
                continue
            else:
                break
        return response


    def _delete(self, url, headers):
        for round in range(self.retries):
            try:
                response = requests.delete(url, headers=headers, verify=False, auth=(self.idrac_username, self.idrac_password))
            except requests.exceptions.SSLError:
                continue
            except requests.exceptions.ConnectionError:
                # there might be some other polling activity blocking this
                time.sleep(5)
                continue
            else:
                break
        return response 


class bios(drac_base):    
    def __init__(self, module, redfish_uri, op):
        idrac_ip = module.params['idrac']
        idrac_username = module.params["username"]
        idrac_password = module.params["password"]
        tries = int(module.params["retries"])
        super(bios, self).__init__(idrac_ip, idrac_username, idrac_password, tries)

        key_value_pairs_str = None
        if op == "update_bios":
            key_value_pairs_str = module.params["key_value_pairs"]
        elif op == "update_boot_order":
            key_value_pairs_str = module.params["boot_devices"]
        if key_value_pairs_str is not None:
            key_value_pairs_str = re.sub(r'\'', '"', key_value_pairs_str)
            key_value_pairs_str = re.sub(r'True', 'true', key_value_pairs_str)
            key_value_pairs_str = re.sub(r'False', 'false', key_value_pairs_str)
            self.key_value_pairs = json.loads(key_value_pairs_str)
        self.module = module
        self.op = op
        self.root_uri = 'https://%s%s' % (self.idrac_ip, redfish_uri)
        if self.op == "get_idrac_info":
            self.system_uri = self._find_systems_uri()
            self.manager_uri = self._find_managers_uri()


    def _find_systems_uri(self):
        response = self._get(self.root_uri)
        data = response.json()
        systems = data["Systems"]["@odata.id"]
        response = self._get('https://%s%s' % (self.idrac_ip, systems))
        data = response.json()
        for member in data[u'Members']:
            return member[u'@odata.id']


    def _find_managers_uri(self):
        response = self._get(self.root_uri)
        data = response.json()
        managers = data["Managers"]["@odata.id"]
        response = self._get('https://%s%s' % (self.idrac_ip, managers))
        data = response.json()
        for member in data[u'Members']:
            return member[u'@odata.id']
        
 
    def run(self):
        if self.op == "update_bios":
            self.update_bios()
        elif self.op == "get_idrac_info":
            self.get_idrac_info()
        elif self.op == "update_boot_order":
            self.update_boot_order()
        else:
            self.module.fail_json(msg="Unsupported operation: %s" % self.op)


    def _get_job_queue(self):
        url = 'https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs' % self.idrac_ip
        response = self._get(url)
        job_queue = re.findall("JID_.+?'", str(response.json()))
        jobs = [job.strip("}").strip("\"").strip("'") for job in job_queue]
        return jobs 


    def _clear_job_queue(self):
        job_queue = self._get_job_queue()
        if len(job_queue) > 0:
            url = 'https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs' % self.idrac_ip
            headers = {"content-type": "application/json"}
            for job in job_queue:
                job = job.strip("'")
                url = 'https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs/%s' % (self.idrac_ip, job)
                self._delete(url, headers)


    def wait_for_job_status(self, job_id, expected_msg):
        url = 'https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs/%s' % (self.idrac_ip, job_id)
        for round in range(100):
            req = self._get(url)
            statusCode = req.status_code
            data = req.json()
            if statusCode != 200:
                self.module.fail_json(msg="check job status failed with code %s, detail: %s" %(statusCode, data))
            if data[u'Message'] == expected_msg:
                return 
            else:
                time.sleep(10)
        self.module.fail_json(msg="check job status timeout") 


    def reboot(self):
        # returns code, message
        response = requests.get('https://%s/redfish/v1/Systems/System.Embedded.1/' % self.idrac_ip,verify=False,auth=(self.idrac_username, self.idrac_password))   
        data = response.json()
        if data[u'PowerState'] == "On":
            url = 'https://%s/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset' % self.idrac_ip
            payload = {'ResetType': 'GracefulShutdown'}
            headers = {'content-type': 'application/json'}
            response = self._post(url, payload, headers)
            statusCode = response.status_code
            if statusCode == 204:
                time.sleep(10)
            else:
                return statusCode, "Failed to gracefully power OFF, details: {0}".format(response.json())
            while True:
                response = self._get('https://%s/redfish/v1/Systems/System.Embedded.1/' % self.idrac_ip)
                data = response.json()
                if data[u'PowerState'] == "Off":
                    break
                else:
                    continue
            payload = {'ResetType': 'On'}
            headers = {'content-type': 'application/json'}
            response = self._post(url, payload, headers)
            statusCode = response.status_code
            if statusCode == 204:
                return 0, "reboot success" 
            else:
                return statusCode, "Failed to power ON, details: {0}".format(response.json())
        elif data[u'PowerState'] == "Off":
            url = 'https://%s/redfish/v1/Systems/System.Embedded.1/Actions/ComputerSystem.Reset' % self.idrac_ip
            payload = {'ResetType': 'On'}
            headers = {'content-type': 'application/json'}
            response = self._post(url, payload, headers)
            statusCode = response.status_code
            if statusCode == 204:
                return 0, "reboot success"
            else:
                return statusCode, "Failed to power ON, details: {0}".format(response.json())
        else:
            return 1, "Failed to get current power state"


    def get_bios(self):
        response = self._get('https://%s/redfish/v1/Systems/System.Embedded.1/Bios' % self.idrac_ip)
        if response.status_code != 200:
            self.module.fail_json(msg="Incompatible iDRAC version")
        return response.json() 


    def get_job_id(self):
        url = 'https://%s/redfish/v1/Managers/iDRAC.Embedded.1/Jobs' % self.idrac_ip
        payload = {"TargetSettingsURI":"/redfish/v1/Systems/System.Embedded.1/Bios/Settings"}
        headers = {'content-type': 'application/json'}
        response = self._post(url, payload, headers)
        statusCode = response.status_code
        if statusCode != 200:
            self.module.fail_json(msg="Create BIOS setting Job failed with code %s, details: %s" % (statusCode, response.json()))
        d=str(response.__dict__)
        z=re.search("JID_.+?,",d).group()
        job_id=re.sub("[,']","",z)
        return job_id 


    def update_bios(self):
        data = self.get_bios() 
        payload = {"Attributes":{}}
        for key in self.key_value_pairs:
            # only update the setting if current value is different
            if data['Attributes'][key] != self.key_value_pairs[key]:
                payload["Attributes"][key] = self.key_value_pairs[key]
        #if nothing to update, skip
        if len(payload["Attributes"]) == 0:
            self.module.exit_json(changed=False, msg="nothing to change")

        self._clear_job_queue()
        url = 'https://%s/redfish/v1/Systems/System.Embedded.1/Bios/Settings' % self.idrac_ip
        headers = {'content-type': 'application/json'}
        response = self._patch(url, payload, headers)
        statusCode = response.status_code
        if statusCode != 200:
            self.module.fail_json(msg="BIOS setting failed with error code %s, details: %s" % (statusCode, response.json()))

        job_id = self.get_job_id()
        self.wait_for_job_status(job_id, "Task successfully scheduled.")
       
        # reboot to complete the job
        code, msg = self.reboot()
        if code != 0:
            self.module.fail_json(msg="reboot failed with code %s, detail: %s" %(code, msg))
        else:
            self.wait_for_job_status(job_id, "Job completed successfully.")
            self.module.exit_json(changed=True, result="success", msg="bios updated and server rebooted")


    def update_boot_order(self):
        data = self.get_bios()
        current_boot_mode = data[u'Attributes']["BootMode"]

        response = self._get('https://%s/redfish/v1/Systems/System.Embedded.1/BootSources' % self.idrac_ip)
        data = response.json()
        if data[u'Attributes'] == {}:
            self.module.fail_json(msg="no %s boot order devices detected for iDRAC IP %s" % (current_boot_mode,idrac_ip))

        if current_boot_mode == "Uefi":
            boot_seq = "UefiBootSeq"
        else:
            boot_seq = "BootSeq"

        current_boot_devices = data[u'Attributes'][boot_seq]
        if any(x !=y for x, y in zip(current_boot_devices, self.key_value_pairs)):
            pass
        else:
            # if current boot order list is equal to required, do nothing
            self.module.exit_json(changed=False, msg="nothing to change")

        self._clear_job_queue()
        url = 'https://%s/redfish/v1/Systems/System.Embedded.1/BootSources/Settings' % self.idrac_ip
        payload = {'Attributes': {boot_seq:self.key_value_pairs}}
        headers = {'content-type': 'application/json'}
        response = self._patch(url, payload, headers)
        statusCode = response.status_code
        if statusCode != 200:
            self.module.fail_json(msg="Failed to change boot device error code %s, details: %s" % (statusCode, response.json()))

        job_id = self.get_job_id()
        self.wait_for_job_status(job_id, "Task successfully scheduled.")

        # reboot to complete the job
        code, msg = self.reboot()
        if code != 0:
            self.module.fail_json(msg="reboot failed with code %s, detail: %s" %(code, msg))
        else:
            self.wait_for_job_status(job_id, "Job completed successfully.")
            self.module.exit_json(changed=True, result="success", msg="boot order updated and server rebooted")


    def get_idrac_info(self):
        response = self._get('https://%s%s/EthernetInterfaces' %(self.idrac_ip, self.manager_uri))
        statusCode = response.status_code
        if statusCode != 200:
            self.module.fail_json(msg="Failed to access %s, details: %s" % (self.manager_uri, response.json()))
        data = response.json()
        url = data['Members'][0][u'@odata.id']
        response = self._get('https://%s%s' %(self.idrac_ip, url))
        statusCode = response.status_code
        if statusCode != 200:
            self.module.fail_json(msg="Failed to access %s, details: %s" % (url, response.json()))
        data = response.json()
        self.module.exit_json(changed=False, result="success", mac_address=data['MACAddress'])

