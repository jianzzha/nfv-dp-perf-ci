#!/usr/bin/env python
# usuage: script input_yaml_file vars.yaml vars.ini
import sys
import yaml

if len(sys.argv) != 3:
    sys.exit("script expects a yaml file for input and one output file!")

with open(sys.argv[1], 'r') as ymlfile:
    cfg = yaml.load(ymlfile)

with open("vars.yaml", 'r') as varfile:
    vars = yaml.load(varfile)

if cfg["SYSTEM_RUNNING_ON"] == "KVM":
    sys.exit("baremetal is expected to clone CPU allocation info!")

core_list = cfg["AVAILABLE_DATA_CORES"].split(',')
numa = int(cfg["DATA_NIC_NUMA"])
thread_per_core = int(cfg["THREAD_PER_CORE"])

# build nova_vcpu list
nova_vcpu_list = []
iter = 3
if thread_per_core == 2:
    cpu0_siblings_list = cfg["CPU0_SIBLINGS"].split(',')
    siblings_distance = int(cpu0_siblings_list[1]) - int(cpu0_siblings_list[0])
    # allocate 6 HT for VM, that's two by three on sibling core
    while iter > 0:
        thread = core_list.pop(0)
        sibling = str(int(thread) + siblings_distance)
        if sibling in core_list:
            sibling_index = core_list.index(sibling)
            core_list.pop(sibling_index)
        else:
            sys.exit("failed to find {0:s}' sibling from {1:s}".format(thread, core_list))
        nova_vcpu_list.append(thread)
        nova_vcpu_list.append(sibling)
        iter -= 1

else:
    siblings_distance = 0
    while iter > 0:
        thread = core_list.pop(0)
        nova_vcpu_list.append(thread)
        iter -= 1

with open(sys.argv[2], 'w') as ofile:
    ofile.write("THREAD_PER_CORE={0:d}\n".format(thread_per_core))
    ofile.write("ISOLATED_CPU_LIST={0:s}\n".format(cfg["AVAILABLE_DATA_CORES"]))
    ofile.write("NOVA_CPU_LIST={0:s}\n".format(','.join(nova_vcpu_list)))

    # in case of ovs-pmd repin, let's get that list as well
    if vars["TEST_ITEM"] == "dpdk" and vars["REPIN_OVS_PMD"] == "true":
        for i in range(2):
            pmd_vm_eth = core_list.pop(0)
            ofile.write("PMD_DATA_ETH{0:s}={1:s}\n".format(i, pmd_vm_eth))
            if thread_per_core == 2:
                pmd_dpdk = str(int(pmd_vm_eth) + siblings_distance)
                pmd_dpdk_index = core_list.index(pmd_dpdk)
                core_list.pop(pmd_dpdk_index)
                ofile.write("PMD_DATA_DPDK{0:s}={1:s}\n".format(i, pmd_dpdk))
            else:
                ofile.write("PMD_DATA_DPDK{0:s}={1:s}\n".format(i, pmd_vm_eth))
        access_numa = int(cfg["ACCESS_NIC_NUMA"])
        if access_numa == numa:
            access_core_list = core_list
        else:
            access_core_list = cfg["AVAILABLE_ACCESS_CORES"].split(',')
        pmd_vm_eth = access_core_list.pop(0)
        ofile.write("PMD_ACCESS_ETH={0:s}\n".format(pmd_vm_eth))
        # for access port, use the same core for both threads
        ofile.write("PMD_ACCESS_DPDK={0:s}\n".format(pmd_vm_eth))

        #resreve one core for lcore
        ofile.write("OVS_LCORE={0:s}\n".format(core_list.pop(0)))

 
