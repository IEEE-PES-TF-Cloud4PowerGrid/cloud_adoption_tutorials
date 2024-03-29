# Aggregating and Managing DERs at Scale through the Cloud

## Introduction
This tutorial demonstrates a ***simplistic case*** of aggregating Distributed Energy Resources (DERs) and managing them at scale for wholesale electricity market bidding.

The solution meets the following requirements
* Connect to heterogenous distributed energy resources (DERs) at scale
* Collect device measurements such as power output and run time every 5 min (minimum req: 5 min, most RT energy markets settle every 5 min)
* Keep data for 5 years for auditing and forensic purpose
* Analyze data via structured queries on-demand and periodically
* Visualize data thru charts on dashboard
* Identify the time slots when the aggregated capacity >= 100 kW (minimum size requirement for aggregated DERs in market participation)
* Keep the cost low
* Anomaly detection and automatic notification
* Back up data in a different geographic region

## Caveat
The solution is neither a utility prototype nor an abstraction of any vendor's offering (not even close). It is just intended to showcase how a cloud native design is capable of addressing the business needs involved in DER aggregation and management.

## Solution Architecture Diagram
![solution arch diagram](docs/managing_ders_at_scale_soln_arch.png?raw=true "Solution Architecture for Cloud-based DER Aggregation and Management")
### Service Used
* AWS IoT Core
* AWS IoT Greengrass
* AWS Kinesis (alternative: AWS MSK, i.e.,AWS Managed Streaming for Apache Kafka)
* AWS Glue
* AWS S3
* AWS Athena
* AWS QuickSight
* AWS SNS
* AWS KMS
* AWS CloudWatch
* AWS CloudTrail
* AWS IAM

## Dashboard
### Charts of Unaggregated Metrics
![der unaggregated](docs/DER_unaggregated.png?raw=true "Charts of Unaggregated metrics")

### DER aggregated power output
![der aggregated](docs/DER_aggregated.png?raw=true "DER aggregated power output")


##  Installing and Configuring Prerequisites
Check [here](https://github.com/nvm-sh/nvm) to learn how to install Node.js and npm

Install the AWS CDK Toolkit globally using the following Node Package Manager command.
```ini
npm install -g aws-cdk
```
Run the following command to verify correct installation and print the version number of the AWS CDK.
```ini
cdk --version
```
Create a CDK project in your project folder
```ini
cdk init der-management --language=typescript
```

## Bootstrapping
Deploying stacks with the AWS CDK requires dedicated Amazon S3 buckets and other containers to be available to AWS CloudFormation during deployment. Creating these is called [bootstrapping](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html). To bootstrap, issue:
```ini
cdk bootstrap aws://${ACCOUNT-ID}/${AWS-REGION}
```

## Build CDK Project
To build the project, run the command below
```ini
cdk synth
```
To deploy the template that you synthesized with CDK synth in an AWS account, run the following command. You may need to install AWS CLI on the build machine and set up an AWS profile
```ini
cdk deploy
```

If you wish to remove the stack from your AWS account, then run the following command
```ini
cdk destroy
```