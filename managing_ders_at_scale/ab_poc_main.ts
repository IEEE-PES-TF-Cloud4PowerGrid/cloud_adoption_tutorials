import * as cdk from '../../../iot_builder_retreat/project-iota/node_modules/aws-cdk-lib';
import { CreateIoTSimStack } from './stacks/create_iot_sim_stack_v3';
// import { CreateIoTSimStack } from './stacks/create_iot_sim_stack';
import { CreateStorageStack } from './stacks/create_storage_stack';

const app = new cdk.App();

const storageStack = new CreateStorageStack(app, 'CreateStorageStack');

// This stack depends on the S3 stack
new CreateIoTSimStack(app, 'CreateIoTSimStack', {
    s3BucketName: storageStack.s3BucketName,
    s3BucketArn: storageStack.s3BucketArn,
});
// new CreateIoTSimStack(app, 'CreateIoTSimStack')