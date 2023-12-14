# Power Grid Simulator on Elastic HPC Cluster

## Introduction
This tutorial guides you through the deployment of an elastic HPC cluster on AWS for power grid simulations using AWS ParallelCluster

## Deployment Step
1. Follow the instructions provided by [AWS official documentation](https://docs.aws.amazon.com/parallelcluster/latest/ug/install-v3.html) to install AWS ParallelCluster SDK first

2. Create an IAM user with the two inline policies attached using the two json files in this repo
    * CreateRoles4ParallelCluster - use [pcluster_creator_iaminlinepolicy_advuser.json](https://github.com/IEEE-PES-TF-Cloud4PowerGrid/tutorials/blob/main/elastic_simulation_cluster/pcluster_creator_iaminlinepolicy_advuser.json)
    * BaseUser4ParallelCluster - use [pcluster_creator_iaminlinepolicy_baseuser.json](https://github.com/IEEE-PES-TF-Cloud4PowerGrid/tutorials/blob/main/elastic_simulation_cluster/pcluster_creator_iaminlinepolicy_baseuser.json)

3. Configure the awscli with the IAM user created in step 2

4. Modify the template config file [cluster-config-template.yaml](https://github.com/IEEE-PES-TF-Cloud4PowerGrid/tutorials/blob/main/elastic_simulation_cluster/cluster-config-template.yaml) by following the in-file instructions and save it as "cluster-config.yaml"

5. Run the following command:

	```
    pcluster create-cluster --cluster-name [any cluster name] --cluster-configuration cluster-config.yaml
    ```

6. Use the following command to inspect the cluster status

	```
    plcuster describe-cluster --cluster-name [the cluster name]
    ```
	
7. When you see the cluster status becomes *CREATE_COMPLETE* (this may take a few minutes), use the following command to SSH into the cluster head node

	```
    pcluster ssh -i pcluster.pem --cluster-name [the cluster name]
    ```
	
8. Create an IAM user with only AWS managed policy "AmazonEC2ReadOnlyAccess" and "CloudWatchFullAccess" attached, download the access key pair

9. Navigate to the path "$HOME/aws-parallelcluster-monitoring/prometheus/" on the head node, open the file "prometheus.yml", replace the <your AWS access key> and <your AWS secret key> with the values in the key file created in step 8

10. Create a file named "credentials", and enter the following content (replace the string in the angle brackets, including the brackets with the values from the key file created in step 8):
    ```
	[default]
	aws_access_key_id=<your AWS access key>
	aws_secret_access_key=<your AWS secret key>
    ```
	
11. Create a file named "config", and enter the following content (replace <your AWS Region> with desired region name, e.g., *us-east-1*, *us-west-2*):
    ```
	[default]
	region = <your AWS Region>
	output = json
    ```
	
12. Run the following command:
    ```
	sudo docker-compose --env-file /etc/parallelcluster/cfnconfig -f $HOME/aws-parallelcluster-monitoring/docker-compose/docker-compose.master.yml -p monitoring-master down
	sudo docker-compose --env-file /etc/parallelcluster/cfnconfig -f $HOME/aws-parallelcluster-monitoring/docker-compose/docker-compose.master.yml -p monitoring-master up -d
	sudo docker cp credentials grafana:/usr/share/grafana/.aws/
	sudo docker cp config grafana:/usr/share/grafana/.aws/
    ```
	
13. when the cluster is up, go to **Network & Security**, then **Security Groups** display, find the security group named *"HeadNodeSecurityGroup"*, write down its group ID, e.g., *"sg-01774f7001ec6c72d"*, add inbound rules using the following commands
    ```
	aws ec2 authorize-security-group-ingress --group-id [your security group id] --protocol tcp --port 80 --cidr 0.0.0.0/0
	aws ec2 authorize-security-group-ingress --group-id [your security group id] --protocol tcp --port 443 --cidr 0.0.0.0/0
    ```
	
Now you can open the cluster home page by visiting the head node public IPv4 address. You will see the cluster main page as shown below.

## Cluster Main Page
![Cluster main page](img/ClusterMainPage.png?raw=true "ParallelCluster for power grid simulation")

