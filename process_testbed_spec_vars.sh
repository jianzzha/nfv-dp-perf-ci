#!/usr/bin/env bash

set -eux -o pipefail

# Prepare ansible inventory file
echo "[undercloud]" | tee -a hosts
echo "${UNDERCLOUD} ansible_user=root ansible_ssh_pass=${SSH_PASSWORD}" | tee -a hosts
echo "[trafficgen]" | tee -a hosts
echo "${TREX_HOST} ansible_user=root ansible_ssh_pass=${SSH_PASSWORD}" | tee -a hosts

if [[ ${TESTBED:-x} == 'x' ]]; then
    echo "var TESTBED not defined!"
    exit 1
fi

# if testbed is defined, use that testbed spec as the base var.yaml
if [[ ${TESTBED:-x} != 'x' ]]; then
   cp files/${TESTBED}.yaml vars.yaml
fi

cat << EOF >> vars.yaml
---
DISABLE_CVE: ${DISABLE_CVE}
TEST_ITEM: ${TEST_ITEM}
UNDERCLOUD: ${UNDERCLOUD}
TREX_HOST: ${TREX_HOST}
DOCKER_IMG_TAG: ${DOCKER_IMG_TAG}
SSH_PASSWORD: ${SSH_PASSWORD}
VM_IMAGE_URL: ${VM_IMAGE_URL}
ACCESS_NETWORK_TYPE: ${ACCESS_NETWORK_TYPE}
ACCESS_NETWORK_VLAN: ${ACCESS_NETWORK_VLAN}
DATA_NETWORK_TYPE: ${DATA_NETWORK_TYPE}
DATA_NETWORK_VLAN_1: ${DATA_NETWORK_VLAN_1}
DATA_NETWORK_VLAN_2: ${DATA_NETWORK_VLAN_2}
PACKET_LOSS_RATIO: ${PACKET_LOSS_RATIO}
PACKET_SIZE: ${PACKET_SIZE}
SEARCH_TIME: ${SEARCH_TIME}
VALIDATION_TIME: ${VALIDATION_TIME}
FLOWS: ${FLOWS}
FIX_TUNED_AFTER_DEPLOY: ${FIX_TUNED_AFTER_DEPLOY}
CPU_ALLOCATION: ${CPU_ALLOCATION}
ENABLE_HT: ${ENABLE_HT}
EOF

chmod u+x cpu_allocation.py
if [[ ${CPU_ALLOCATION} == "same_as_trex" ]]; then
    ansible-playbook -i hosts -e "baremetal=trafficgen" get_cpuinfo.yaml
elif [[ ${CPU_ALLOCATION} == "same_as_undercloud" ]]; then
    ansible-playbook -i hosts -e "baremetal=undercloud" get_cpuinfo.yaml
fi
 
if [[ ${CPU_ALLOCATION} != "manual" ]]; then
    ./cpu_allocation.py ci_sysinfo.yaml cpu_resource.out
    source cpu_resource.out
    sed -i -e "s/ISOLATED_CPU_LIST: .*/ISOLATED_CPU_LIST: ${ISOLATED_CPU_LIST}/" vars.yaml
    sed -i -e "s/NOVA_CPU_LIST: .*/NOVA_CPU_LIST: ${NOVA_CPU_LIST}/" vars.yaml

    # decide if hyperthreading enabled based on how many thread per core collected from remote
    if [[ ${THREAD_PER_CORE} == "2" && ${ENABLE_HT} == "false" ]]; then
        echo "expecting non HT but HT is enabled"
        exit 1
    fi
    if [[ ${THREAD_PER_CORE} == "1" && ${ENABLE_HT} == "true" ]]; then
        echo "expecting HT but HT is disabled"
        exit 1
    fi

    if [[ ${PMD_DATA_ETH0:-x} != 'x' ]]; then
        sed -i -e "s/PMD_ACCESS_ETH: .*/PMD_ACCESS_ETH: ${PMD_ACCESS_ETH}/" vars.yaml
        sed -i -e "s/PMD_ACCESS_DPDK: .*/PMD_ACCESS_DPDK: ${PMD_ACCESS_DPDK}/" vars.yaml
        sed -i -e "s/PMD_DATA_ETH0: .*/PMD_DATA_ETH0: ${PMD_DATA_ETH0}/" vars.yaml
        sed -i -e "s/PMD_DATA_DPDK0: .*/PMD_DATA_DPDK0: ${PMD_DATA_DPDK0}/" vars.yaml
        sed -i -e "s/PMD_DATA_ETH1: .*/PMD_DATA_ETH1: ${PMD_DATA_ETH1}/" vars.yaml
        sed -i -e "s/PMD_DATA_DPDK1: .*/PMD_DATA_DPDK1: ${PMD_DATA_DPDK1}/" vars.yaml
        sed -i -e "s/PMD_CORE_LIST: .*/PMD_CORE_LIST: ${PMD_DATA_ETH0},${PMD_DATA_ETH1},${PMD_DATA_DPDK0},${PMD_DATA_DPDK1}/" vars.yaml
        sed -i -e "s/OVS_LCORE: .*/OVS_LCORE: ${OVS_LCORE}/" vars.yaml
    fi
fi

cat vars.yaml | sed -e '/---/d' -e 's/: /=/' > parameters
 
