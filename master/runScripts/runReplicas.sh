#!/bin/bash

configFile=""
if [ "$#" -eq  "0" ]
    then
        configFile="local1"
else
        configFile=$1
fi

scriptDir="$(dirname $0)"
relativePath="/../paxos/config/$configFile"
configPath=$scriptDir$relativePath

python paxos/send.py 1 0 $configPath -n 4 -c 0 &
python paxos/send.py 1 1 $configPath -n 4 -c 0 &
python paxos/send.py 1 2 $configPath -n 4 -c 0 &