#!/usr/bin/bash

source parameters

pbench-trafficgen --config=nfv-ci-trial --samples=1 --frame-sizes=${PACKET_SIZE} --num-flows=${FLOWS} --traffic-directions=bidirectional --traffic-generator=trex-txrx --devices=${TREX_PCI_ADDR_NIC_1},${TREX_PCI_ADDR_NIC_2} --max-loss-pct=${PACKET_LOSS_RATIO} --skip-git-pull --search-runtime=${SEARCH_TIME} --validation-runtime=${VALIDATION_TIME} -- --send-teaching-warmup --teaching-warmup-packet-type=icmp

# touch this file to indicate the test is done
touch completed
