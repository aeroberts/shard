#!/bin/bash

configFile=""
if [ "$#" -eq  "0" ]
    then
        configFile="local"
else
        configFile=$1
fi

scriptDir="$(dirname $0)"
relativePath="/../config/$configFile"
configPath=$scriptDir$relativePath

python startMaster.py 4 1 $configPath
