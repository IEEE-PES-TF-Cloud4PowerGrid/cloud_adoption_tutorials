#!/bin/bash

#################################
###### install andes ############
#################################

# change user to ec2-user
# sudo su - ec2-user
echo "This is a post-install script"
# install andes
python3 -m pip install andes --user
#cd $HOME
#git clone https://github.com/cuihantao/andes
#pip3 install -r requirements.txt
#pip3 install -r requirements-dev.txt
#python3 -m pip install -e .
# run selftest
python3 -m andes selftest

#######################################################################
##### install grafana and prometheus for monitoring dashboard #########
#######################################################################

#Load AWS Parallelcluster environment variables
. /etc/parallelcluster/cfnconfig

#get GitHub repo to clone and the installation script
#monitoring_url=$(echo ${cfn_postinstall_args}| cut -d ',' -f 1 )
#monitoring_dir_name=$(echo ${cfn_postinstall_args}| cut -d ',' -f 2 )
#fix array annotation
monitoring_url=${cfn_postinstall_args[0]}
monitoring_dir_name=${cfn_postinstall_args[1]}
monitoring_tarball="${monitoring_dir_name}.tar.gz"
#setup_command=$(echo ${cfn_postinstall_args}| cut -d ',' -f 3 )
setup_command=${cfn_postinstall_args[2]}
monitoring_home="/home/${cfn_cluster_user}/${monitoring_dir_name}"

case ${cfn_node_type} in
    HeadNode)
        wget ${monitoring_url} -O ${monitoring_tarball}
        mkdir -p ${monitoring_home}
        tar xvf ${monitoring_tarball} -C ${monitoring_home} --strip-components 1
    ;;
    ComputeFleet)

    ;;
esac

#Execute the monitoring installation script
bash -x "${monitoring_home}/parallelcluster-setup/${setup_command}" >/tmp/monitoring-setup.log 2>&1
exit $?
