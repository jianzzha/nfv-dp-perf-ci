#/bin/bash
# create n Vms, n specified by the first augument
set -x
export ANSIBLE_HOST_KEY_CHECKING=False

error ()
{
  echo $* 1>&2
  exit 1
}

function delete_nfv_instances () {
  source ${overcloudrc} || error "can't load overcloudrc"
  echo "delete instances"
  for id in $(openstack server list \
                 | egrep "demo" \
                 | awk -F'|' '{print $2}' \
                 | awk '{print $1}'); do
    openstack server delete $id
  done

  echo "delete unused ports"
  for id in $(neutron port-list | grep ip_address \
                                | egrep -v '10.1.1.1"|10.1.1.2"' \
                                | awk -F'|' '{print $2}' \
                                | awk '{print $1}'); do
    neutron port-delete $id
  done

  echo "delete provider subnets"
  for id in $(neutron subnet-list | grep provider \
                                  | awk -F'|' '{print $2}' \
                                  | awk '{print $1}'); do
    neutron subnet-delete $id
  done

  echo "delete provider nets"
  for id in $(neutron net-list | grep provider \
                               | awk -F'|' '{print $2}' \
                               | awk '{print $1}'); do
    neutron net-delete $id
  done

}

function get_vm_mac() {
# arg1: vm name
# arg2: network name
  local vm=$1
  local net=$2
  local vm_ip=$(openstack server show $vm | sed -n -r "s/.*$net=([.0-9]+).*/\1/p")
  local mac=$(neutron port-list --fixed_ips ip_address=${vm_ip} \
              | sed -n -r "s/.*([a-f0-9]{2}:[a-f0-9]{2}:[a-f0-9]{2}:[a-f0-9]{2}:[a-f0-9]{2}:[a-f0-9]{2}).*/\1/p")
  echo $mac
}

function get_mac_from_pci_slot () {
  #this function retrieve mac address from pci slot id. $1: slot number, $2: variable name to set the return value to
  local slot=$1
  local  __resultvar=$2
  local line=$(sudo dpdk-devbind -s | grep $slot)
  local kernel_driver
  local mac 
  if echo $line | grep igb; then
    kernel_driver=igb
  elif echo $line | grep i40e; then
    kernel_driver=i40e
  elif echo $line | grep ixgbe; then
    kernel_driver=ixgbe
  else
    error "failed to find kernel driver for pci slot $slot"
  fi

  # bind it to kernel to see what its mac address
  sudo dpdk-devbind -u $slot
  sudo dpdk-devbind -b ${kernel_driver} $slot
  mac=$(sudo dmesg | sed -r -n "s/.*${slot}:.*([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})/\1/p" | tail -1)
  eval $__resultvar=$mac
  # bind the port back to vfio-pci driver
  lsmod | grep vfio_pci || sudo modprobe vfio-pci
  sudo dpdk-devbind -b vfio-pci $slot
}


function start_instance() {
# arg1: instance name 
# arg2: provider 1 port-id
# arg3: provider 2 port-id
# arg4: access port-id
  local name=$1
  local id1=$2
  local id2=$3
  local id3=$4

  local opt=""
  local hypervisor=""
  if [[ ! -z "$compute_node" ]]; then
    # is the node name even right? need full name(with domain) 
    hypervisor=$(openstack hypervisor list | grep $compute_node | awk '{print $4}')
    if [[ ! -z "hypervisor" ]]; then
      opt="$opt --availability-zone nova:$hypervisor"
    fi
  fi

  if [[ ! -z "$user_data" ]]; then
    opt="$opt --user-data $user_data"
  fi

  openstack server create --flavor nfv \
                          --image nfv \
                          --nic port-id="$id3" \
                          --nic port-id="$id1" \
                          --nic port-id="$id2" \
                          --key-name demo-key \
                          $opt $name 

  if [[ $? -ne 0 ]]; then
    echo nova boot failed
    exit 1
  fi
  echo instance $name started
}

function check_input() {
  if [ -z ${num_vm+x} ]; then
    echo "num_vm not set, default to: 1"
    num_vm=1
  fi
  if (( num_vm > 99 )); then
    error "num_vm: ${num_vm} invalid, can not exceed 99"
  fi

  if [ -z ${num_flows+x} ]; then
    echo "num_flows not set, default to: 128"
    num_flows=128
  fi

  if [ -z ${vm_vcpu_count+x} ]; then
    echo "vm_vcpu_count not set, default to: 6"
    vm_vcpu_count=6
  fi
  if (( vm_vcpu_count < 6 )); then
    error "vm_vcpu_count: ${vm_vcpu_count} invalid, needs at least 6"
  fi

  if [ -z ${enable_multi_queue+x} ]; then
    enable_multi_queue=false
  fi
 
  if [ -z ${provider_network_type+x} ]; then 
    echo "provider_network_type not set, default to: flat"
    provider_network_type="flat"
  fi

  if [ -z ${access_network_type+x} ]; then
    echo "access_network_type not set, default to flat"
    access_network_type="flat"
  fi

  if [[ ${provider_network_type} == "vlan" ]]; then
    if [[ -z "${data_vlan_start}" ]]; then
      echo "data_vlan_start not set, use default: 100"
      data_vlan_start=100
    fi
  elif [[ ${provider_network_type} == "vxlan" ]]; then
    if [[ -z "${data_vxlan_start}" ]]; then
      echo "data_vxlan_start not set, use default: 100"
      data_vxlan_start=100
    fi
  elif [[ ${provider_network_type} == "flat" ]]; then
    if [[ ${access_network_type} == "shared" ]]; then
      # sharing access and data network on the same port require vlan network type
      error "to use shared access_network_type, provider_network_type has to be vlan"
    fi
  else
    error "invalid provider_network_type: ${provider_network_type}"
  fi 

  if [[ ${access_network_type} == "vlan" || ${access_network_type} == "shared" ]]; then
    if [[ -z "${access_network_vlan}" ]]; then
      echo "access_network_vlan not set, use default: 200"
      access_network_vlan=200
    fi
  elif [[ ${access_network_type} != "flat" ]]; then
    error "invalid access_network_type: ${access_network_type}"
  fi

  if [[ "$routing" == "testpmd" && "${vnic_type}" == "sriov" ]]; then
    routing="testpmd-sriov"
  fi 

  if [[ "$routing" == "testpmd" || "$routing" == "testpmd-sriov" ]]; then
    if [[ -z ${testpmd_fwd} ]]; then
      testpmd_fwd="io"
    fi
    case ${testpmd_fwd} in
      io|mac) ;;
      macswap)
        traffic_direction="unidirec"
        traffic_gen_dst_slot=${traffic_gen_src_slot}
        ;;
      *)
        error "invalid testpmd fwd: ${testpmd_fwd}"i
        ;;
    esac
  fi

  case ${traffic_direction} in
    bidirec|unidirec|revunidirec);;
    *) error "invalid traffic_direction: ${traffic_direction}";;
  esac

  if [ -z ${traffic_gen_extra_opt+x} ]; then 
    #traffic_gen_extra_opt unset
    traffic_gen_extra_opt=""
  fi 

  if [ -z ${stop_pbench_after+x}]; then
    stop_pbench_after="false"
  fi
}

function stop_pbench () {
  if [ -z "${traffic_gen_remote_addr}" ]; then
    sudo "PATH=$PATH" sh -c pbench-kill-tools 
    sudo "PATH=$PATH" sh -c pbench-clear-tools
  else
    ssh root@${traffic_gen_remote_addr} "pbench-kill-tools; pbench-clear-tools"
  fi
}

function start_pbench () {
 
  stop_pbench
  source ${stackrc} || error "can't load stackrc"
  echo "start tools on computes"
  for node in $(nova list | sed -n -r 's/.*compute.*ctlplane=([.0-9]+).*/\1/ p'); do
    for tool in ${pbench_comupte_tools}; do
      if [ -z "${traffic_gen_remote_addr}" ]; then
        sudo "PATH=$PATH" sh -c "pbench-register-tool --remote=$node --name=$tool"
      else
        ssh root@${traffic_gen_remote_addr} "pbench-register-tool --remote=$node --name=$tool"
      fi
    done
  done

  echo "start tools on VMs"
  source ${overcloudrc} || error "can't load overcloudrc"
  for i in $(seq ${num_vm}); do
    for tool in ${pbench_vm_tools}; do
      if [ -z "${traffic_gen_remote_addr}" ]; then
        sudo "PATH=$PATH" sh -c "pbench-register-tool --remote=demo$i --name=$tool"
      else
        ssh root@${traffic_gen_remote_addr} "pbench-register-tool --remote=demo$i --name=$tool"
      fi
    done
  done
}
 
 
SCRIPT_PATH=$(dirname $0)             # relative
SCRIPT_PATH=$(cd $SCRIPT_PATH && pwd)  # absolutized and normalized

if [ ! -z "$1" ]; then
  cfg_file=$1
else
  cfg_file=nfv_test.cfg
fi

echo "##### loading $cfg_file"
if [ ! -f ${SCRIPT_PATH}/${cfg_file} ]; then
  error "${cfg_file} can't be found"
fi
source ${SCRIPT_PATH}/${cfg_file}

# when comparing string, ignore case
shopt -s nocasematch

source ${SCRIPT_PATH}/core_util_functions

# sanity check input parameters
echo "##### sanity check input parameters" 
check_input

# delete exisitng NFV instances and cleanup networks
echo "##### deleting existing nfv instances"
delete_nfv_instances

source ${overcloudrc} || error "can't load overcloudrc"

# we have to delete existing: multi-queue test has peroperty setting on image and can impact single-queue test
if openstack image list --name nfv | grep nfv; then
  echo "##### deleting nfv image"
  openstack image delete nfv
fi

echo "##### building instance image"
if ! openstack image list --name nfv | grep nfv; then
  #glance has no such an image listed, we need to upload it to glance
  #does the local image directory exists
  if [ ! -d /tmp/nfv ]; then
    echo "directory /tmp/nfv not exits, creating"
    mkdir -p /tmp/nfv || error "failed to create /tmp/nfv"
  fi

  #download image if it not exits on local directory
  if [ -f /tmp/nfv/nfv.qcow2 ]; then
    echo "found image /tmp/nfv/nfv.qcow2"
  else 
    echo "image /tmp/nfv/nfv.qcow2 not found, fetching"
    # is the url pointing to local directory?
    if [[ "$vm_image_url" =~ ^https?: ]]; then
      wget $vm_image_url -O /tmp/nfv/nfv.qcow2 || error "failed to download image"
    elif [[ -f $vm_image_url ]]; then
      cp $vm_image_url /tmp/nfv/nfv.qcow2
    else
      error "invalid url: $vm_image_url"
    fi
  fi

  openstack image create --disk-format qcow2 --container-format bare   --public --file /tmp/nfv/nfv.qcow2 nfv || error "failed to create image" 
fi

#update nova quota to allow more core use and more network
echo "##### updating project quota"
project_id=$(openstack project show -f value -c id admin)
nova quota-update --instances $num_vm $project_id
nova quota-update --cores $(( $num_vm * 10 )) $project_id
neutron quota-update --tenant_id $project_id --network $(( $num_vm + 2 ))
neutron quota-update --tenant_id $project_id --subnet $(( $num_vm + 2 ))

echo "##### adding keypair"
nova keypair-list | grep 'demo-key' || nova keypair-add --pub-key ~/.ssh/id_rsa.pub demo-key
openstack security group rule list | grep 22:22 || openstack security group rule create default --protocol tcp --dst-port 22:22 --src-ip 0.0.0.0/0
openstack security group rule list | grep icmp || openstack security group rule create default --protocol icmp

echo "##### deleting exisitng nfv flavor"
if openstack flavor list | grep nfv; then
  openstack flavor delete nfv
fi

#  default vm_vcpu_count=6 to make sure the HT sibling not used by instance; an alternative, might be used hw:cpu_thread_policy=isolate, --vcpus 3 (rather than 6)
echo "##### creating nfv flavor"

openstack flavor create nfv --id 1 --ram 8192 --disk 20 --vcpus ${vm_vcpu_count} 

# no need to set numa topo
#  nova flavor-key 1 set hw:cpu_policy=dedicated \
#                        hw:mem_page_size=1GB \
#                        hw:numa_nodes=1 \
#                        hw:numa_mempolicy=strict \
#                        hw:numa_cpus.0=0,1,2,3,4,5 \
#                        hw:numa_mem.0=4096

nova flavor-key 1 set hw:cpu_policy=dedicated \
                      hw:mem_page_size=1GB

if [[ ${repin_kvm_emulator} == "false" ]]; then
  nova flavor-key 1 set hw:emulator_threads_policy=isolate
fi

if [[ ${enable_HT} == "true" ]]; then
  nova flavor-key 1 set hw:cpu_thread_policy=require
fi

if [[ ${enable_multi_queue} == "true" ]]; then
  nova flavor-key 1 set vif_multiqueue_enabled=true
  openstack image set nfv --property hw_vif_multiqueue_enabled=true
fi

echo "##### creating instance access network"
if ! neutron net-list | grep access; then
  if [[ ${access_network_type} == "flat" ]]; then
    neutron net-create access --provider:network_type flat \
                              --provider:physical_network access \
                              --port_security_enabled=False
  elif [[ ${access_network_type} == "vlan" ]]; then
    neutron net-create access --provider:network_type vlan \
                              --provider:physical_network access \
                              --provider:segmentation_id ${access_network_vlan} \
                              --port_security_enabled=False
  else
    error "access_network_type wrong"
  fi
  neutron subnet-create --name access --dns-nameserver ${dns_server} access 10.1.1.0/24
fi

echo "##### creating instance provider networks"
for i in 0 1; do
    # the ooo templates is using sriov1/2 for data network; sriov0/1.
    if [[ ${provider_network_type} == "flat" ]]; then
        provider_opt="--provider:network_type flat"
    elif [[ ${provider_network_type} == "vlan" ]]; then
        var=data_network_vlan_$i
        provider_opt="--provider:network_type vlan \
                      --provider:segmentation_id ${!var}"
    else
        error "invalid provider_network_type: ${provider_network_type}"
    fi
    
    if [[ ${vnic_type} == "sriov" ]]; then
        neutron net-create provider-nfv$i ${provider_opt} \
                                          --provider:physical_network sriov$i \
                                          --port_security_enabled=False
    else
        neutron net-create provider-nfv$i ${provider_opt} \
                                          --provider:physical_network dpdk$i \
                                          --port_security_enabled=False
    fi
    
    neutron subnet-create --name provider-nfv$i \
                            --disable-dhcp \
                            --gateway 20.$i.0.1 \
                            provider-nfv$i 20.$i.0.0/16
    
done

if [[ ${vnic_type} == "sriov" ]]; then
  vnic_option="--vnic-type direct"
else
  vnic_option=""
fi

echo "##### starting instances"
provider0=$(openstack port create --network provider-nfv0 ${vnic_option} nfv0-port | awk '/ id/ {print $4}')
provider1=$(openstack port create --network provider-nfv1 ${vnic_option} nfv1-port | awk '/ id/ {print $4}')
access=$(openstack port create --network access access-port | awk '/ id/ {print $4}')
# make sure port created complete before start the instance
start_instance demo1 $provider0 $provider1 $access

# JZ debug insertion
#exit 0

echo "##### waiting for instances go live"
vmState=0
for n in {0..1000}; do
  sleep 2
  if openstack server list | egrep 'demo1.*ACTIVE'; then
      vmState=1
      break
  elif openstack server list | egrep 'demo1.*ERROR'; then
      break
  fi
done

if [ $vmState -ne 1 ]; then
  error "failed to start guest"
fi

#### JZ test point ####
#exit 0

# update /etc/hosts entry with instances
echo "##### update /etc/hosts entry with instance names"
sudo sed -i -r '/demo1/d' /etc/hosts
nova list | sudo sed -n -r 's/.*(demo1).*access=([.0-9]+).*/\2 \1/p' | sudo tee --append /etc/hosts >/dev/null

# remove old entries in known_hosts
echo "##### remove old entries in known_hosts"
sudo sed -i -r "/demo1/d" /root/.ssh/known_hosts
sudo sed -i -r "/demo1/d" /home/stack/.ssh/known_hosts
vm_ip=$(grep demo1 /etc/hosts | awk '{print $1}')
sudo sed -i -r "/${vm_ip}/d" /root/.ssh/known_hosts
sudo sed -i -r "/${vm_ip}/d" /home/stack/.ssh/known_hosts

# record all VM's access info in ansible inventory file
nodes=${SCRIPT_PATH}/nodes

echo "##### record ansible hosts access info in $nodes"
echo "[VMs]" > $nodes 
nova list | sed -n -r 's/.*(demo1).*access=([.0-9]+).*/\1 ansible_host=\2/ p' >> $nodes

cat <<EOF >>$nodes
[VMs:vars]
ansible_connection=ssh 
ansible_user=root
ansible_ssh_pass=password
ansible_become=true
EOF

source $stackrc || error "can't load stackrc"
echo "[computes]" >> $nodes
nova list | sed -n -r 's/.*compute.*ctlplane=([.0-9]+).*/\1/ p' >> $nodes
echo "[controllers]" >> $nodes
nova list | sed -n -r 's/.*control.*ctlplane=([.0-9]+).*/\1/ p' >> $nodes
cat <<EOF >>$nodes
[computes:vars]
ansible_connection=ssh
ansible_user=heat-admin
ansible_become=true
[controllers:vars]
ansible_connection=ssh
ansible_user=heat-admin
ansible_become=true
EOF

echo "##### repin threads on compute nodes"
if [[ $vnic_type == "sriov" ]]; then
  ansible-playbook -i $nodes ${SCRIPT_PATH}/repin_threads.yml --extra-vars "repin_kvm_emulator=${repin_kvm_emulator}" || error "failed to repin thread"
else
  pmd_core_list="$pmd_vm_eth0,$pmd_vm_eth1,$pmd_vm_eth2,$pmd_dpdk0,$pmd_dpdk1,$pmd_dpdk2,$spare_cores"
  pmd_core_mask=`get_cpumask $pmd_core_list`
  ansible-playbook -i $nodes ${SCRIPT_PATH}/repin_threads.yml --extra-vars "repin_ovs_nonpmd=${repin_ovs_nonpmd} repin_kvm_emulator=${repin_kvm_emulator} repin_ovs_pmd=${repin_ovs_pmd} pmd_vm_eth0=${pmd_vm_eth0} pmd_vm_eth1=${pmd_vm_eth1} pmd_vm_eth2=${pmd_vm_eth2} pmd_dpdk0=${pmd_dpdk0} pmd_dpdk1=${pmd_dpdk1} pmd_dpdk2=${pmd_dpdk2} pmd_core_mask=${pmd_core_mask}" || error "failed to repin thread"
fi

# check all VM are reachable by ping
# try 30 times
echo "##### testing instances access via ping"
for n in $(seq 30); do
  reachable=1
  ping -q -c5 demo1 || reachable=0
  if [ $reachable -eq 1 ]; then
    break
  fi
  sleep 1
done      

[ $reachable -eq 1 ] || error "not all VM pingable"

# make sure remote ssh port is open
echo "##### testing instances access via ssh"
for n in $(seq 90); do
  reachable=1
  timeout 1 bash -c "cat < /dev/null > /dev/tcp/demo1/22" || reachable=0
  if [ $reachable -eq 1 ]; then
    break
  fi
  sleep 1
done

[ $reachable -eq 1 ] || error "not all VM ssh port open"

###### JZ test point
#exit 0

# upload ssh key to all $nodes. if cloud-init user-data is supplied, no need to update VMs 
echo "##### update authorized ssh key"
groups=(computes controllers VMs)

for host in ${groups[@]}; do
  if [[ "$USER" == "stack" ]]; then
    ANSIBLE_HOST_KEY_CHECKING=False UserKnownHostsFile=/dev/null ansible $host -i $nodes -m shell -a "if [[ ! -e /root/.ssh ]]; then mkdir -p /root/.ssh; fi; > /root/.ssh/authorized_keys; echo $(sudo cat /home/stack/.ssh/id_rsa.pub) >> /root/.ssh/authorized_keys; echo $(sudo cat /root/.ssh/id_rsa.pub) >> /root/.ssh/authorized_keys"
    ANSIBLE_HOST_KEY_CHECKING=False UserKnownHostsFile=/dev/null ansible $host -i $nodes -m lineinfile -a "name=/etc/ssh/sshd_config regexp='^UseDNS' line='UseDNS no'"
    ANSIBLE_HOST_KEY_CHECKING=False UserKnownHostsFile=/dev/null ansible $host -i $nodes -m service -a "name=sshd state=restarted"
  else
    sudo -u stack ANSIBLE_HOST_KEY_CHECKING=False UserKnownHostsFile=/dev/null ansible $host -i $nodes -m shell -a "if [[ ! -e /root/.ssh ]]; then mkdir -p /root/.ssh; fi; > /root/.ssh/authorized_keys; echo $(sudo cat /home/stack/.ssh/id_rsa.pub) >> /root/.ssh/authorized_keys; echo $(sudo cat /root/.ssh/id_rsa.pub) >> /root/.ssh/authorized_keys"
    sudo -u stack ANSIBLE_HOST_KEY_CHECKING=False UserKnownHostsFile=/dev/null ansible $host -i $nodes -m lineinfile -a "name=/etc/ssh/sshd_config regexp='^UseDNS' line='UseDNS no'"
    sudo -u stack ANSIBLE_HOST_KEY_CHECKING=False UserKnownHostsFile=/dev/null ansible $host -i $nodes -m service -a "name=sshd state=restarted"
  fi
done

echo "##### provision nfv work load"
ansible-playbook -i $nodes start_testpmd.yaml
ansible-playbook -i $nodes install_pbench_agent.yaml
start_pbench
