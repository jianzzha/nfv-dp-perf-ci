#!/usr/bin/env python
# usuage: script compute_data cpu_resource.out 
import sys
import json
import yaml
import re

def next_thread_pair(cpus, numa):
    global cpu_index
    while True:
        cpu = cpus[cpu_index]
        cpu_index += 1
        # skip cpu 0 as that's the housekeeping cpu
        if cpu['numa_node'] == numa and 0 not in cpu['thread_siblings']:
            return cpu['thread_siblings']
         

if len(sys.argv) != 2:
    sys.exit("script expects a json file!")

with open(sys.argv[1], 'r') as iFile:
    cfg = json.load(iFile)

with open("vars.yaml", 'r') as varfile:
    vars = yaml.load(varfile)

# find the nic numa node
nics = cfg['numa_topology']['nics']
for nic in nics:
    if (vars['DATA_NIC_1'] == nic['name']):
        data_numa_node = nic['numa_node']
    if (vars['COMPUTE_ACCESS_PORT'] == nic['name']):
        access_numa_node = nic['numa_node']

cpus = cfg['numa_topology']['cpus']
thread_per_core = len(cpus[0]['thread_siblings'])
if thread_per_core > 1:
    if vars['TEST_ITEM'] == 'rt':
        # rt test require non HT for better result
        sys.exit("Disable hyper thread before proceed RT test")
    # hyper threading enabled
    siblings_distance = cpus[0]['thread_siblings'][1] - cpus[0]['thread_siblings'][0]
else:
    if vars['TEST_ITEM'] == 'dpdk' or vars['TEST_ITEM'] == 'sriov':
        # dpdk or sriov test require hyper threading enabled
        sys.exit("Disable hyper threading before proceed sriov or dpdk test")

cpu_index = 0
if vars['TEST_ITEM'] == 'dpdk':
    dpdk0_cpu, vhost0_cpu = next_thread_pair(cpus, data_numa_node) 
    dpdk1_cpu, vhost1_cpu = next_thread_pair(cpus, data_numa_node)
    if access_numa_node == data_numa_node:
        # dpdk2_cpu, vhost2_cpu for access port
        dpdk2_cpu, vhost2_cpu = next_thread_pair(cpus, data_numa_node)
    else:
        saved_index = cpu_index
        cpu_index = 0
        dpdk2_cpu, vhost2_cpu = next_thread_pair(cpus, access_numa_node)
        cpu_index = saved_index
    ovs_pmd_core_list = [dpdk0_cpu, vhost0_cpu, dpdk1_cpu, vhost1_cpu, dpdk2_cpu, vhost2_cpu]

# dpdk or sriov will need 4 pairs of threads, 3 for vcpu, 1 for kvm
# rt will need 5 pairs of threads, 4 for vcpu, 1 for kvm
if vars['TEST_ITEM'] == 'rt':
    rounds = 5
else:
    rounds = 4

nova_vcpu_list = []
while rounds > 0:
    nova_vcpu_list += next_thread_pair(cpus, data_numa_node)
    rounds -= 1

ovs_lcore = next_thread_pair(cpus, data_numa_node)

interfaces = cfg['inventory']['interfaces']
for interface in interfaces:
    if interface['name'] == vars['DATA_NIC_1']:
        # "product": "0x1017"
        product = re.sub('^0x', '', interface['product'])
        # "vendor": "0x15b3"
        vendor = re.sub('^0x', '', interface['vendor'])
        break

with open('vars.yaml', 'r') as varfile:
    lines = varfile.readlines()

with open('vars.yaml', 'w') as varfile:
    for line in lines:
        if re.match('DATA_NIC_VENDOR', line) is not None:
            varfile.write('DATA_NIC_VENDOR: "%s"\n' % (vendor + ':' + product))
        elif re.match('ISOLATED_CPU_LIST', line) is not None:
            varfile.write("ISOLATED_CPU_LIST: {0:s}\n".format(','.join(map(str, ovs_pmd_core_list + nova_vcpu_list + ovs_lcore))))
        elif re.match('NOVA_CPU_LIST', line) is not None:
            varfile.write("NOVA_CPU_LIST: {0:s}\n".format(','.join(map(str, nova_vcpu_list))))
        
        elif re.match('OVS_LCORE', line) is not None and vars["TEST_ITEM"] == "dpdk":
            
            varfile.write("OVS_LCORE: {0:s}\n".format(','.join(map(str, ovs_lcore))))
        elif re.match('PMD_DATA_ETH0', line) is not None and vars["TEST_ITEM"] == "dpdk":
            varfile.write("PMD_DATA_ETH0: %d\n" % vhost0_cpu)
        elif re.match('PMD_DATA_ETH1', line) is not None and vars["TEST_ITEM"] == "dpdk":
            varfile.write("PMD_DATA_ETH1: %d\n" % vhost1_cpu)
        elif re.match('PMD_DATA_DPDK0', line) is not None and vars["TEST_ITEM"] == "dpdk":
            varfile.write("PMD_DATA_DPDK0: %d\n" % dpdk0_cpu)
        elif re.match('PMD_DATA_DPDK1', line) is not None and vars["TEST_ITEM"] == "dpdk":
            varfile.write("PMD_DATA_DPDK1: %d\n" % dpdk1_cpu)
        elif re.match('PMD_ACCESS_ETH', line) is not None and vars["TEST_ITEM"] == "dpdk":
            varfile.write("PMD_ACCESS_ETH: %d\n" % vhost2_cpu)
        elif re.match('PMD_ACCESS_DPDK', line) is not None and vars["TEST_ITEM"] == "dpdk":
            varfile.write("PMD_ACCESS_DPDK: %d\n" % dpdk2_cpu)
        elif re.match('PMD_CORE_LIST', line) is not None and vars["TEST_ITEM"] == "dpdk":
            varfile.write("PMD_CORE_LIST: {0:s}\n".format(','.join(map(str, ovs_pmd_core_list))))
        else:
            varfile.write(line)

