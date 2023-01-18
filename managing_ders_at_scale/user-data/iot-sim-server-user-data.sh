#!/bin/bash -xe
# stop the script on error
set -e

# install jq
sudo yum install -y jq
# install git
sudo yum install -y git
# install pip
sudo yum install -y pip
# set region for awscli 
aws configure set region us-east-1

# generate a private key using openssl
openssl genrsa -out iot_thing.key 4096
# generate a CSR file
openssl req -nodes -newkey rsa:2048 -key iot_thing.key -out iot_thing.csr -subj "/C=GB/ST=Virtual/L=Virtual/O=Global Security/OU=AWS Energy/CN=example.com"
# request a X.509 certificate using the CSR file
aws iot create-certificate-from-csr --certificate-signing-request=file://iot_thing.csr | jq '.certificateArn' > cert_arn.txt

cert_arn=$(cat cert_arn.txt)
cert_arn=$(sed -e 's/^"//' -e 's/"$//' <<<"$cert_arn")
cert_id=$(cat cert_arn.txt | jq '. | split("/")'[-1])
cert_id=$(sed -e 's/^"//' -e 's/"$//' <<<"$cert_id")

# create a json file to formulate the policy
cat <<EOC > iot_thing_policy.json
{
    "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iot:Publish",
        "iot:Receive"
      ],
      "Resource": [
        "arn:aws:iot:us-east-1:291001254992:topic/sdk/test/Python",
        "arn:aws:iot:us-east-1:291001254992:topic/DER/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "iot:Subscribe"
      ],
      "Resource": [
        "arn:aws:iot:us-east-1:291001254992:topicfilter/sdk/test/Python",
        "arn:aws:iot:us-east-1:291001254992:topicfilter/DER/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "iot:Connect"
      ],
      "Resource": [
        "arn:aws:iot:us-east-1:291001254992:client/sdk-java",
        "arn:aws:iot:us-east-1:291001254992:client/DER*",
        "arn:aws:iot:us-east-1:291001254992:client/sdk-nodejs-*"
      ]
    }
  ]
}
EOC

instance_id=$(curl http://169.254.169.254/latest/meta-data/instance-id)
# get the device type for this machine
device_type=$(aws ec2 describe-tags --filters \
    Name=resource-type,Values=instance Name=resource-id,Values=$instance_id Name=key,Values=DeviceType | jq '.Tags[].Value')
# get rid of double quote
device_type=$(sed -e 's/^"//' -e 's/"$//' <<<"$device_type")
# get the device sequence number for this machine
device_seq=$(aws ec2 describe-tags --filters \
    Name=resource-type,Values=instance Name=resource-id,Values=$instance_id Name=key,Values=DeviceSeqNum | jq '.Tags[].Value')
# get rid of double quote
device_seq=$(sed -e 's/^"//' -e 's/"$//' <<<"$device_seq")

# set a IoT name
thing_name="DER-"$device_type"-"$device_seq
# create a IoT thing (virtual device)
aws iot create-thing --thing-name $thing_name
# create a thing group
thing_group=$(aws iot list-thing-groups | jq '.thingGroups | .[].groupName')
if [ -z "$thing_group" ] || [[ "$thing_group" != *"$device_type"* ]]; then
    aws iot create-thing-group --thing-group-name $device_type
else
    echo "thing group $device_type has already existed"
fi
# attach the thing to the thing group
aws iot add-thing-to-thing-group --thing-group-name $device_type --thing-name $thing_name

# attach a certificate
aws iot attach-thing-principal --principal $cert_arn --thing-name $thing_name
# create a policy
policy_name=$(aws iot list-policies | jq '.policies | .[].policyName')
if [ -z "$policy_name" ] || [[ "$policy_name" != *"iot_thing_policy"* ]]; then
    aws iot create-policy --policy-name iot_thing_policy --policy-document file://iot_thing_policy.json
else
    echo "policy 'iot_thing_policy' has already existed"
fi
# attach a policy to the certificate
aws iot attach-policy --target $cert_arn --policy-name iot_thing_policy
# update the certificate status to ACTIVE
aws iot update-certificate --certificate-id $cert_id --new-status ACTIVE
# get the endpoint address
endpoint_addr=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS | jq '.endpointAddress')
endpoint_addr=$(sed -e 's/^"//' -e 's/"$//' <<<"$endpoint_addr")
# get the certificate pem
cert_pem=$(aws iot describe-certificate --certificate-id $cert_id | jq '.certificateDescription.certificatePem')
# get rid of double quote
cert_pem=$(sed -e 's/^"//' -e 's/"$//' <<<"$cert_pem")
# print a new line instead of "\n" in the certificate file
echo -e $cert_pem > iot_thing.cert.pem


# prepare the IoT SDK
# Check to see if root CA file exists, download if not
if [ ! -f ./root-CA.crt ]; then
  printf "\nDownloading AWS IoT Root CA certificate from AWS...\n"
  curl https://www.amazontrust.com/repository/AmazonRootCA1.pem > root-CA.crt
fi

# Check to see if AWS Device SDK for Python exists, download if not
if [ ! -d ./aws-iot-device-sdk-python-v2 ]; then
  printf "\nCloning the AWS SDK...\n"
  git clone https://github.com/aws/aws-iot-device-sdk-python-v2.git
fi

# Check to see if AWS Device SDK for Python is already installed, install if not
# if ! python -c "import AWSIoTPythonSDK" &> /dev/null; then
#   printf "\nInstalling AWS SDK...\n"
#   pushd aws-iot-device-sdk-python
#   pip install AWSIoTPythonSDK
#   result=$?
#   popd
#   if [ $result -ne 0 ]; then
#     printf "\nERROR: Failed to install SDK.\n"
#     exit $result
#   fi
# fi

if ! python3 -c "import awscrt" &> /dev/null; then
  printf "\nInstalling AWS SDK...\n"
  pushd aws-iot-device-sdk-python-v2
  python3 -m pip install awsiotsdk
  result=$?
  popd
  if [ $result -ne 0 ]; then
    printf "\nERROR: Failed to install SDK.\n"
    exit $result
  fi
fi

# install numpy and scipy
python3 -m pip install numpy
python3 -m pip install scipy

# copy the metrics definition file from s3 bucket here
# get the name of dedicated s3 bucket
s3_bucket=$(aws ec2 describe-tags --filters \
    Name=resource-type,Values=instance Name=resource-id,Values=$instance_id Name=key,Values=AccessS3Bucket | jq '.Tags[].Value')
# get rid of double quote
s3_bucket=$(sed -e 's/^"//' -e 's/"$//' <<<"$s3_bucket")
#aws s3 ls s3://$s3_bucket/metrics_def.json && aws s3 cp s3://$s3_bucket/metrics_def.json .
#aws s3 ls s3://$s3_bucket/iot_device_data_generator_v2.py && aws s3 cp s3://$s3_bucket/iot_device_data_generator_v2.py .
#aws s3 ls s3://$s3_bucket/der_class.py && aws s3 cp s3://$s3_bucket/der_class.py .
aws s3 cp s3://$s3_bucket/ . --recursive --include "*.*"
cp aws-iot-device-sdk-python-v2/samples/command_line_utils.py .
# run pub/sub app using certificates downloaded in package
printf "\nRunning pub/sub application...\n"
nohup python3 iot_device_data_generator_v2.py --endpoint $endpoint_addr --ca_file root-CA.crt \
    --cert iot_thing.cert.pem --key iot_thing.key --client_id $thing_name --device_type $device_type --topic DER/"$device_type" --count 0 &



