#!/bin/bash -xe
# exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

export DEBIAN_FRONTEND=noninteractive
export AWSRegion="us-east-1"
export ThingGroup="windfarm_gg"

echo "Installing OS updates"
sudo apt-get update -yq
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -yq
sudo apt install unzip -y

echo "Installing Dependencies"
sudo apt install python3-pip -y

sudo pip3 install --upgrade pip
sudo pip3 install boto3
sudo pip3 install numpy --ignore-installed
sudo pip3 install scipy --ignore-installed

sudo apt-get -y install jq

curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

echo "Installing Java"
sudo apt install default-jdk -yq
sudo ln -s /usr/bin/java /usr/bin/java11

echo "Installing Greengrass v2"
cd ~/
sudo adduser --system ggc_user
sudo groupadd --system ggc_group

wget -O- https://apt.corretto.aws/corretto.key | sudo apt-key add -
sudo apt-get install software-properties-common -y
sudo add-apt-repository 'deb https://apt.corretto.aws stable main'
sudo apt-get update; sudo apt-get install -y java-11-amazon-corretto-jdk

export instance_id=$(curl http://169.254.169.254/latest/meta-data/instance-id)

export s3_bucket=$(aws ec2 describe-tags --filters \
    Name=resource-type,Values=instance Name=resource-id,Values=$instance_id Name=key,Values=AccessS3Bucket | jq '.Tags[].Value')
# get rid of double quote
export s3_bucket=$(sed -e 's/^"//' -e 's/"$//' <<<"$s3_bucket")

# get the device type for this machine
export device_type=$(aws ec2 describe-tags --filters \
    Name=resource-type,Values=instance Name=resource-id,Values=$instance_id Name=key,Values=DeviceType | jq '.Tags[].Value')
# get rid of double quote
export device_type=$(sed -e 's/^"//' -e 's/"$//' <<<"$device_type")
# get the device sequence number for this machine
export device_seq=$(aws ec2 describe-tags --filters \
    Name=resource-type,Values=instance Name=resource-id,Values=$instance_id Name=key,Values=DeviceSeqNum | jq '.Tags[].Value')
# get rid of double quote
export device_seq=$(sed -e 's/^"//' -e 's/"$//' <<<"$device_seq")

export CoreName="DER-"$device_type"-"$device_seq

echo "Installing Greengrass Nucleus"
curl -s https://d2s8p88vqu9w66.cloudfront.net/releases/greengrass-nucleus-latest.zip > greengrass-nucleus-latest.zip
unzip greengrass-nucleus-latest.zip -d GreengrassInstaller && rm greengrass-nucleus-latest.zip
sudo -E java -Droot=/greengrass/v2 -Dlog.store=FILE -jar ./GreengrassInstaller/lib/Greengrass.jar --aws-region $AWSRegion --thing-name $CoreName --thing-group-name $ThingGroup --component-default-user ggc_user:ggc_group --provision true --setup-system-service true --deploy-dev-tools true

echo "Installing gdk"
python3 -m pip install -U git+https://github.com/aws-greengrass/aws-greengrass-gdk-cli.git@v1.1.0
# add gdk to the system path
PATH=/home/ubuntu/.local/bin:$PATH

# sleep 5

echo "Building Greengrass components"
echo "building iot core publisher component"
cd ~/
mkdir -p greengrassv2/IPCPublish
cd greengrassv2/IPCPublish
# create a json file to formulate the component definition
cat <<EOC > gdk-config.json
{
    "component": {
      "com.ipc.publish": {
        "author": "songaws",
        "version": "NEXT_PATCH",
        "build": {
          "build_system": "zip"
        },
        "publish": {
          "bucket": "greengrass-component-artifacts",
          "region": "us-east-1"
        }
      }
    },
    "gdk_version": "1.0.0"
}
EOC

# create the recipe
cat <<EOC > recipe.yaml
---
RecipeFormatVersion: "2020-01-25"
ComponentName: "{COMPONENT_NAME}"
ComponentVersion: "{COMPONENT_VERSION}"
ComponentDescription: "This is an IPC publish component written in Python."
ComponentPublisher: "{COMPONENT_AUTHOR}"
ComponentConfiguration:
  DefaultConfiguration:
    accessControl:
      aws.greengrass.ipc.mqttproxy:
        com.ipc.publish:mqttproxy:1:
          policyDescription: Allows access to publish to all AWS IoT Core topics.
          operations:
            - aws.greengrass#PublishToIoTCore
          resources:
            - '*'
Manifests:
  - Platform:
      os: all
    Artifacts:
      - URI: "s3://BUCKET_NAME/COMPONENT_NAME/COMPONENT_VERSION/IPCPublish.zip"
        Unarchive: ZIP
    Lifecycle:
      Install: "pip3 install awsiotsdk numpy scipy"
      Run: "python3 -u {artifacts:decompressedPath}/IPCPublish/gg_device_data_generator.py"
EOC

aws s3 ls s3://$s3_bucket/metrics_def.json && aws s3 cp s3://$s3_bucket/metrics_def.json .
aws s3 ls s3://$s3_bucket/gg_device_data_generator.py && aws s3 cp s3://$s3_bucket/gg_device_data_generator.py .
aws s3 ls s3://$s3_bucket/der_class.py && aws s3 cp s3://$s3_bucket/der_class.py .
aws s3 ls s3://$s3_bucket/speed2power.csv && aws s3 cp s3://$s3_bucket/speed2power.csv .

gdk component build
gdk component publish

export iot_pub_com_version=$(aws greengrassv2 list-components | jq -r ".[] | .[] | select(.componentName==\"com.ipc.publish\") | .latestVersion | .componentVersion")

echo "building local publisher component"
cd ~/
mkdir -p greengrassv2/IPCLocalPublish
cd greengrassv2/IPCLocalPublish

# create a json file to formulate the component definition
cat <<EOC > gdk-config.json
{
    "component": {
      "com.ipc.local.publish": {
        "author": "songaws",
        "version": "NEXT_PATCH",
        "build": {
          "build_system": "zip"
        },
        "publish": {
          "bucket": "greengrass-component-artifacts",
          "region": "us-east-1"
        }
      }
    },
    "gdk_version": "1.0.0"
}
EOC

# create the recipe
cat <<EOC > recipe.yaml
---
RecipeFormatVersion: "2020-01-25"
ComponentName: "{COMPONENT_NAME}"
ComponentVersion: "{COMPONENT_VERSION}"
ComponentDescription: "This is an IPC local publish component written in Python."
ComponentPublisher: "{COMPONENT_AUTHOR}"
ComponentConfiguration:
  DefaultConfiguration:
    accessControl:
      aws.greengrass.ipc.pubsub:
        com.ipc.local.publish:pubsub:1:
          policyDescription: Allows access to publish to all AWS IoT Core topics.
          operations:
            - aws.greengrass#PublishToTopic
          resources:
            - '*'
Manifests:
  - Platform:
      os: all
    Artifacts:
      - URI: "s3://BUCKET_NAME/COMPONENT_NAME/COMPONENT_VERSION/IPCLocalPublish.zip"
        Unarchive: ZIP
    Lifecycle:
      Install: "pip3 install awsiotsdk"
      Run: "python3 -u {artifacts:decompressedPath}/IPCLocalPublish/gg_device_local_publisher.py"
EOC

aws s3 ls s3://$s3_bucket/gg_device_local_publisher.py && aws s3 cp s3://$s3_bucket/gg_device_local_publisher.py .

gdk component build
gdk component publish

export local_pub_com_version=$(aws greengrassv2 list-components | jq -r ".[] | .[] | select(.componentName==\"com.ipc.local.publish\") | .latestVersion | .componentVersion")

echo "building local subscriber component"
cd ~/
mkdir -p greengrassv2/IPCLocalSubscribe
cd greengrassv2/IPCLocalSubscribe
# create a json file to formulate the component definition
cat <<EOC > gdk-config.json
{
    "component": {
      "com.ipc.local.subscribe": {
        "author": "songaws",
        "version": "NEXT_PATCH",
        "build": {
          "build_system": "zip"
        },
        "publish": {
          "bucket": "greengrass-component-artifacts",
          "region": "us-east-1"
        }
      }
    },
    "gdk_version": "1.0.0"
}
EOC

# create the recipe
cat <<EOC > recipe.yaml
---
RecipeFormatVersion: "2020-01-25"
ComponentName: "{COMPONENT_NAME}"
ComponentVersion: "{COMPONENT_VERSION}"
ComponentDescription: "This is an IPC subscribe component written in Python."
ComponentPublisher: "{COMPONENT_AUTHOR}"
ComponentConfiguration:
  DefaultConfiguration:
    accessControl:
      aws.greengrass.ipc.pubsub:
        com.ipc.local.subscribe:pubsub:1:
          policyDescription: Allows access to publish to all AWS IoT Core topics.
          operations:
            - aws.greengrass#SubscribeToTopic
          resources:
            - '*'
Manifests:
  - Platform:
      os: all
    Artifacts:
      - URI: "s3://BUCKET_NAME/COMPONENT_NAME/COMPONENT_VERSION/IPCLocalSubscribe.zip"
        Unarchive: ZIP
    Lifecycle:
      Install: "pip3 install awsiotsdk"
      Run: "python3 -u {artifacts:decompressedPath}/IPCLocalSubscribe/gg_device_local_subscriber.py"
EOC

aws s3 ls s3://$s3_bucket/gg_device_local_subscriber.py && aws s3 cp s3://$s3_bucket/gg_device_local_subscriber.py .

gdk component build
gdk component publish

export local_sub_com_version=$(aws greengrassv2 list-components | jq -r ".[] | .[] | select(.componentName==\"com.ipc.local.subscribe\") | .latestVersion | .componentVersion")

# get the deployment id for the core device
export deployment_id=$(aws greengrassv2 list-deployments | jq -r ".[] | .[] | select(.targetArn | contains(\"$ThingGroup\")) | .deploymentId")

# create the deployment configuration file with unnecessary blocks removed
aws greengrassv2 get-deployment --deployment-id $deployment_id | jq "del(.tags,.deploymentId,.revisionId,.iotJobId,.iotJobArn,.creationTimestamp,.isLatestForTarget,.deploymentStatus)" > deployment.json

# update the deployment configuration with latest version of components
cat deployment.json | jq ".components += {\"com.ipc.publish\": {\"componentVersion\": \"$iot_pub_com_version\"}, \"com.ipc.local.publish\": {\"componentVersion\": \"$local_pub_com_version\"}, \"com.ipc.local.subscribe\": {\"componentVersion\": \"$local_sub_com_version\"}}" > deploymentUpdated.json

# deploy a newer version
echo "Deploying Greengrass with additional components"

aws greengrassv2 create-deployment --cli-input-json file://deploymentUpdated.json

echo "Setup in now Complete!"
