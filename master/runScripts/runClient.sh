#!/bin/bash

configFile=""
if [ "$#" -eq  "0" ]
    then
        configFile="clientLocal"
else
        configFile=$1
fi

scriptDir="$(dirname $0)"
relativePath="/../config/$configFile"
configPath=$scriptDir$relativePath

python masterClient.py $configPath