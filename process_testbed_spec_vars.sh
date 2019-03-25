#!/usr/bin/env bash

set -eux -o pipefail
export ANSIBLE_HOST_KEY_CHECKING=False

# Prepare ansible inventory file
echo "[undercloud]" | tee -a hosts
echo "${UNDERCLOUD} ansible_user=root ansible_ssh_pass=${SSH_PASSWORD}" | tee -a hosts
echo "[trafficgen]" | tee -a hosts
echo "${TREX_HOST} ansible_user=root ansible_ssh_pass=${SSH_PASSWORD}" | tee -a hosts
echo "[idrac]" | tee -a hosts
echo "localhost ansible_connection=local" | tee -a hosts

# if testbed is defined, use that testbed spec as the base var.yaml
if [[ ${TESTBED:-x} != 'x' ]]; then
   cp files/${TESTBED}.yaml vars.yaml
else
    echo "var TESTBED not defined!"
    exit 1
fi

cat << EOF >> vars.yaml
DISABLE_CVE: ${DISABLE_CVE}
TEST_ITEM: ${TEST_ITEM}
UNDERCLOUD: ${UNDERCLOUD}
TREX_HOST: ${TREX_HOST}
DOCKER_IMG_TAG: ${DOCKER_IMG_TAG}
SSH_PASSWORD: ${SSH_PASSWORD}
VM_IMAGE_URL: ${VM_IMAGE_URL}
DATA_NETWORK_TYPE: ${DATA_NETWORK_TYPE}
DATA_NETWORK_VLAN_1: ${DATA_NETWORK_VLAN_1}
DATA_NETWORK_VLAN_2: ${DATA_NETWORK_VLAN_2}
PACKET_LOSS_RATIO: ${PACKET_LOSS_RATIO}
PACKET_SIZE: ${PACKET_SIZE}
SEARCH_TIME: ${SEARCH_TIME}
VALIDATION_TIME: ${VALIDATION_TIME}
FLOWS: ${FLOWS}
FIX_TUNED_AFTER_DEPLOY: ${FIX_TUNED_AFTER_DEPLOY}
TESTBED: ${TESTBED}
CPU_ALLOCATION: ${CPU_ALLOCATION}
ENABLE_HT: ${ENABLE_HT}
REPIN_OVS_PMD: ${REPIN_OVS_PMD}
REPIN_EMULATOR: ${REPIN_EMULATOR}
UNDERCLOUD_IDRAC: ${UNDERCLOUD_IDRAC:-"NA"}
CONTROLLER_IDRAC: ${CONTROLLER_IDRAC:-"NA"}
COMPUTE_IDRAC: ${COMPUTE_IDRAC:-"NA"}
IDRAC_USER: ${IDRAC_USER}
IDRAC_PASSWORD: ${IDRAC_PASSWORD}
EOF

if [[ ${TESTBED} != "ministack" ]]; then
    # execept ministack, all other testbeds need CONTROLLER_IDRAC and COMPUTE_IDRAC
    if [[ ${CONTROLLER_IDRAC:-"NA"} == "NA" || ${COMPUTE_IDRAC:-"NA"} == "NA" ]]; then
        echo "Needs idrac info for controller and compute nodes"
        exit 1
    fi
fi

# get DNS_SERVER into vars.yaml 
ansible-playbook -i hosts get_undercloud_info.yaml
 
cat vars.yaml | sed -e '/---/d' -e 's/: /=/' > parameters

