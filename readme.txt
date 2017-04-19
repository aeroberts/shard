# shard - EECS 591 Project 2

to run master:

python startMaster.py _path_to_config_file_ 
    -d debug
    -fc filterClient drop first response to client with filter for key
    -fl filterLeader drop first requrest to leader with filter for key
    -r dropRandom randomly drop all sentmenssage %dropRandom of the time
    -nq noQueue No messages from the queue for the initila cluster idea will be sent from the message queue
    -ast addShardTest determinisitically assign new SID
    -dv drop first view of reponses from all clusters

to start paxos cluster:

python paxos/send.py _num_fails_ _replica_id_ _path_to_config_file_
    -n number of clusters (REQUIRED FOR INITIAL SET)
    -c cluster id         (REQUIRED FOR INITIAL SET)
    -d debug
    -s skip sequence number Skip
    -k kill oringinally primary after kill messages are sent
    -q silence noop from log
    -r dropRandom randomly drop all sent messages dropRandom% amount of the time
    
to start client:

python masterClient.py _path_to_config_file_
    -b batch mode supply path to batch file
    -d debug
    -r dropRandom randomly drop all sent messages dropRandom% of the tiem
    -f dropFirst drop first request sent


Example for starting single shard cluster

python startMaster.py config/master/singleNodeLocal -fl x

python paxos/send.py 1 0 config/replica/local1 -n 1 -c 0
python paxos/send.py 1 1 config/replica/local1 -n 1 -c 0
python paxos/send.py 1 2 config/replica/local1 -n 1 -c 0

python masterClient.py config/client/clientLocal
