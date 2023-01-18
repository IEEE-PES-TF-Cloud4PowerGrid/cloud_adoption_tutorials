#!/bin/bash

# get the name of bucket to be deleted
s3bucket2delete=$(aws s3 ls | grep -i createstoragestack | cut -d' ' -f3)
# empty the bucket
aws s3 rm s3://$s3bucket2delete --recursive
# delete the bucket
aws s3 rb s3://$s3bucket2delete --force

# detach the targets (certificates) from policy
policy="iot_thing_policy"
targets=$(aws iot list-targets-for-policy --policy-name $policy | jq ".targets | .[]")
targets=$(sed -e 's/^"//' -e 's/"$//' <<<"$targets")
echo $targets | while read -r target; do aws iot detach-policy --policy-name $policy --target $target; done

# get all things
things=$(aws iot list-things | jq ".[] | .[] | select(.thingName | contains(\"DER-\")) | .thingName")
things=$(sed -e 's/^"//' -e 's/"$//' <<<"$things")

echo $things | while read -r thing; \
do \
echo "detaching principals from $thing"; \
cert_arn=$(aws iot list-thing-principals --thing-name $thing | jq ".[] | .[]"); \
cert_arn=$(sed -e 's/^"//' -e 's/"$//' <<<"$cert_arn"); \
cert_id=$(echo $cert_arn | cut -d'/' -f2); \
aws iot detach-thing-principal --thing-name $thing --principal $cert_arn; \
echo "deactivating certificate $cert_id"; \
aws iot update-certificate --certificate-id $cert_id --new-status INACTIVE; \
echo "deleting certificate $cert_id"; \
aws iot delete-certificate --certificate-id $cert_id; \
echo "deleting thing $thing"; \
aws iot delete-thing --thing-name $thing; \
done

echo "deleting Greengrass core device"
core_device=$(aws greengrassv2 list-core-devices | jq ".coreDevices | .[] | select(.coreDeviceThingName | contains(\"DER-\")) | .coreDeviceThingName")
core_device=$(sed -e 's/^"//' -e 's/"$//' <<<"$core_device")
aws greengrassv2 delete-core-device --core-device-thing-name $core_device
echo "deleting thing group for Greengrass core devices"
aws iot delete-thing-group --thing-group-name windfarm_gg
echo "deleting the policy"
aws iot delete-policy --policy-name $policy

echo "cleanup task completed!"