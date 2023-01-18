import { Stack, StackProps, CfnOutput, Tags } from '../../../../development/node_modules/aws-cdk-lib';
import { Construct } from '../../../../development/node_modules/constructs/lib';
import * as ec2 from '../../../../development/node_modules/aws-cdk-lib/aws-ec2';
import * as iam from '../../../../development/node_modules/aws-cdk-lib/aws-iam';
// import { readFileSync } from 'fs';
import * as fs from "fs"
import * as iot from '../../../../development/node_modules/aws-cdk-lib/aws-iot';
import * as DERData from './user-data/DER2.json';

// AMI: Amazon Linux 2 (latest)
const AmazonLinux2AmiMappings = ec2.MachineImage.genericLinux({
    'us-east-1': 'ami-090fa75af13c156b4'
});

// AMI: Ubuntu (ubuntu-bionic-18.04-amd64-server-20210224)
const UbuntuAmiMappings = ec2.MachineImage.genericLinux({
    'us-east-1': 'ami-013f17f36f8b1fefb'
})

// pre-created key pair
const keyPair = "IoTSimServerKey";

let greengrassComponentBucket:string = "arn:aws:s3:::greengrass-component-artifacts-us-east-1-291001254992";

export interface CreateIoTSimStackProps extends StackProps {
    s3BucketName: string;
    s3BucketArn: string;
}

export class CreateIoTSimStack extends Stack {
    constructor(scope: Construct, id: string, props?: CreateIoTSimStackProps) {
        super(scope, id, props);

        const vpc = new ec2.Vpc(this, 'ab-iot-sim-server-vpc', {
            cidr: '10.0.0.0/16', natGateways: 0,
            subnetConfiguration: [
                { name: 'public', cidrMask: 24, subnetType: ec2.SubnetType.PUBLIC },
            ],
        });

        // security group for IoT device simulation server
        const simServerSG = new ec2.SecurityGroup(this, 'sim-server-sg', {
            vpc, allowAllOutbound: true,
        });
        simServerSG.addIngressRule(
            ec2.Peer.anyIpv4(), ec2.Port.tcp(22), 'Allow SSH access from anywhere',
        );

        // policy for s3 bucket access; applying least privilege pricinple, only request access to the dedicated bucket
        const s3BucketAccessPolicy = new iam.PolicyDocument({
            statements: [
                new iam.PolicyStatement({
                    resources: [props.s3BucketArn, greengrassComponentBucket],
                    actions: ['s3:GetBucketLocation','s3:ListBucket'],
                    effect: iam.Effect.ALLOW,
                }),
                new iam.PolicyStatement({
                    resources: [props.s3BucketArn+'/*', greengrassComponentBucket+'/*'],
                    actions: ['s3:GetObject*','s3:PutObject*','s3:DeleteObject'],
                    effect: iam.Effect.ALLOW,
                }),
                new iam.PolicyStatement({
                    resources: ['*'],
                    actions: ['s3:ListBuckets','s3:CreateBucket'],
                    effect: iam.Effect.ALLOW,
                })
            ],
        })

        //policy for describing tags
        const ec2DescribeTagsPolicy = new iam.PolicyDocument({
            statements: [
                new iam.PolicyStatement({
                    resources: ['*'],                // this action can be only applied to all resources; however, we can use --filter switch to select the desired ones
                    actions: ['ec2:DescribeTags'],
                    effect: iam.Effect.ALLOW,
                })
            ]
        })

        //policy for greengrass
        const greengrassPolicy = new iam.PolicyDocument({
            statements: [
                new iam.PolicyStatement({
                    resources: ['*'],
                    actions: ['logs:*'],
                    effect: iam.Effect.ALLOW,
                }),
                new iam.PolicyStatement({
                    resources: ['*'],
                    actions: ['iot:*'],
                    effect: iam.Effect.ALLOW,
                }),
                new iam.PolicyStatement({
                    resources: ['*'],
                    actions: ['greengrass:*'],
                    effect: iam.Effect.ALLOW,
                }),
                new iam.PolicyStatement({
                    resources: ['*'],
                    actions: ['iam:GetRole*', 'iam:CreateRole*', 'iam:PassRole*', 'iam:CreatePolicy*', 'iam:AttachRolePolicy*', 'iam:GetPolicy*'],
                    effect: iam.Effect.ALLOW,
                }),
            ],
        });

        // role for IoT device simulation server 
        const thingSimServerRole = new iam.Role(this, 'iot-sim-server-role', {
            assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
                iam.ManagedPolicy.fromAwsManagedPolicyName('AWSIoTFullAccess')
            ],
            inlinePolicies: {
                s3BucketAccessPolicy: s3BucketAccessPolicy,
                ec2DescribeTagsPolicy: ec2DescribeTagsPolicy
            }
        });

        // role for Greengrass core device simulation server
        const ggSimServerRole = new iam.Role(this, 'greengrass-sim-server-role', {
            assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
            ],
            inlinePolicies: {
                greengrassPolicy: greengrassPolicy,
                s3BucketAccessPolicy: s3BucketAccessPolicy,
                ec2DescribeTagsPolicy: ec2DescribeTagsPolicy
            }
        });


        // create a fleet of EC2 instances to simulate IoT thing
        var iotDeviceType = DERData['iot_things']['device_type'];
        var ec2IoTSimServerInstance = [];
        var thingServerNum = 0
        for (var i = 0; i < Object.keys(iotDeviceType).length; i++) {
            for (var k = thingServerNum; k < thingServerNum + DERData['iot_things']['device_number'][iotDeviceType[i]]; k++) {
                ec2IoTSimServerInstance[k] = new ec2.Instance(this, 'iot-sim-server-' + k, {
                    vpc,
                    vpcSubnets: {
                        subnetType: ec2.SubnetType.PUBLIC,
                    },
                    role: thingSimServerRole,
                    securityGroup: simServerSG,
                    instanceType: ec2.InstanceType.of(
                        ec2.InstanceClass.BURSTABLE2,
                        ec2.InstanceSize.MEDIUM,
                    ),
                    machineImage: AmazonLinux2AmiMappings,
                    keyName: keyPair,
                });

                // tagging the instance with the device type
                Tags.of(ec2IoTSimServerInstance[k]).add('DeviceType', iotDeviceType[i]);
                Tags.of(ec2IoTSimServerInstance[k]).add('DeviceSeqNum', k.toString());
                Tags.of(ec2IoTSimServerInstance[k]).add('AccessS3Bucket', props.s3BucketName);

                // get the user data from a script as bootstrap
                const iotSimServerUserDataScript = fs.readFileSync('./stacks/user-data/iot-sim-server-user-data.sh', 'utf8');

                // add the user data to the instance
                ec2IoTSimServerInstance[k].addUserData(iotSimServerUserDataScript);
            }
            thingServerNum += DERData['iot_things']['device_number'][iotDeviceType[i]];
        }
        // likewise, create a fleet of EC2 instances to simulate Greengrass (client) devices
        var ggServerNum = 0
        var ggDeviceType = DERData['greengrass_devices']['device_type']
        var ec2GreengrassInstance = [];
        for (var i = 0; i < Object.keys(ggDeviceType).length; i++) {
            for (var k = ggServerNum; k < ggServerNum + DERData['greengrass_devices']['device_number'][ggDeviceType[i]]; k++) {
                ec2GreengrassInstance[k] = new ec2.Instance(this, 'greengrass-sim-server-' + k, {
                    vpc,
                    vpcSubnets: {
                        subnetType: ec2.SubnetType.PUBLIC,
                    },
                    role: ggSimServerRole,
                    securityGroup: simServerSG,
                    instanceType: ec2.InstanceType.of(
                        ec2.InstanceClass.BURSTABLE2,
                        ec2.InstanceSize.MEDIUM,
                    ),
                    machineImage: UbuntuAmiMappings,
                    keyName: keyPair,
                });

                // tagging the instance with the device type
                Tags.of(ec2GreengrassInstance[k]).add('DeviceType', ggDeviceType[i]);
                Tags.of(ec2GreengrassInstance[k]).add('DeviceSeqNum', (thingServerNum+k).toString());
                Tags.of(ec2GreengrassInstance[k]).add('AccessS3Bucket', props.s3BucketName);

                // get the user data from a script as bootstrap
                const ggSimServerUserDataScript = fs.readFileSync('./stacks/user-data/greengrass-sim-server-user-data.sh', 'utf8');

                // add the user data to the instance
                ec2GreengrassInstance[k].addUserData(ggSimServerUserDataScript);
            }
            ggServerNum += DERData['greengrass_devices']['device_number'][ggDeviceType[i]];
        }

    }
}

