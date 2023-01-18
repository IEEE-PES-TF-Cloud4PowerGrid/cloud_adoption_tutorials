import { Stack, StackProps, CfnOutput } from '../../../../development/node_modules/aws-cdk-lib';
import { Construct } from '../../../../development/node_modules/constructs';
import * as s3 from '../../../../development/node_modules/aws-cdk-lib/aws-s3';
import * as s3deploy from '../../../../development/node_modules/aws-cdk-lib/aws-s3-deployment';


export interface StorageStackProps extends StackProps {
    prop: string; // insert props as needed here
  }

export class CreateStorageStack extends Stack {
    public readonly s3BucketName: string;
    public readonly s3BucketArn: string;
    
    constructor(scope: Construct, id: string, props?: StorageStackProps) {
        super(scope, id, props);

        // create a particular s3 bucket
        const s3Bucket = new s3.Bucket(this, 'song-ab-DER-device-metrics-def',{
            encryption: s3.BucketEncryption.S3_MANAGED,
        });

        // add metrics definition to the bucket
        new s3deploy.BucketDeployment(this, 'UploadMetricsDefinition', {
            sources: [
                s3deploy.Source.asset('./stacks/user-data')
                // s3deploy.Source.asset('./stacks/user-data/metrics_def.json'),
                // s3deploy.Source.asset('./stacks/user-data/iot_device_data_generator_v2.py'),
                // s3deploy.Source.asset('./stacks/user-data/der_class.py'),
                // s3deploy.Source.asset('./stacks/user-data/speed2power.csv')
            ],
            destinationBucket: s3Bucket,
        });

        //export the s3 bucket name
        this.s3BucketName =  s3Bucket.bucketName;
        this.s3BucketArn = s3Bucket.bucketArn;
    }
}

