# Deploy Runbook — MSBN Transcript Verification

## Pre-existing manual resources

### AWS Budget

- **Name**: `Total_Budget`
- **Type**: Cost budget, $1,000/month
- **Thresholds** (actual cost):
  - 25% ($250)
  - 50% ($500)
  - 75% ($750)
  - 90% ($900)
- **Subscribers**: all 6 team members on every threshold:
  - Bishal.Bagale@usm.edu
  - Sabin.Baral@usm.edu
  - Saurav.Kandel@usm.edu
  - Shushil.Pant@usm.edu
  - Sudeep.Kumal@usm.edu
  - Sujal.Maharjan@usm.edu
- **Managed in**: AWS Console (Billing > Budgets). NOT managed by CDK.
- If re-deploying to a different AWS account, recreate this budget manually
  to match the configuration above.

## Pre-deploy checklist

1. **Enable Bedrock model access** — In the AWS Console, navigate to
   Amazon Bedrock > Model access (us-east-1). Request and enable access
   for **Amazon Nova Lite** and **Amazon Nova Pro**. The first Extract
   Lambda invocation will fail with `AccessDeniedException` if this is
   not done.

2. **Bootstrap CDK** — Run `cdk bootstrap` if this is the first CDK
   deployment in the target account + region (us-east-1).

3. **Verify SNS subscriptions** — Confirm all 6 team members have clicked
   the AWS confirmation link in their USM email for the budget alert
   SNS topic. Unconfirmed subscribers will not receive budget alerts.

4. **Run tests** — `make test` must pass (all tests green).

5. **Run synth** — `make synth` must produce a clean CloudFormation
   template with no errors.

6. **Verify Extract Lambda image** — Confirm that either:
   - CDK is configured to build the Docker image during deploy
     (default behavior with `DockerImageCode.from_image_asset`), OR
   - The ECR image for the Extract Lambda has been manually built
     and pushed to the account's ECR repository.

## Deploy command

```bash
cdk deploy
```

No context variables are required. The budget is managed manually
outside of CDK.

## Post-deploy verification

1. **Record stack outputs** — After deploy completes, note the
   CloudFormation outputs:
   - `UserPoolId`
   - `UserPoolClientId`
   - `ApiUrl`
   - Region (always `us-east-1`)
   - `BucketName` (from the S3 bucket resource)
   - `TableName` (always `msbn-applications`)

2. **Create test users** — Run:
   ```bash
   python scripts/create_test_users.py
   ```
   This creates three test accounts: `reviewer1`, `reviewer2`, `admin1`.

3. **Upload a test transcript** — Pick one from
   `tests/fixtures/real_transcripts/` and upload it to S3:
   ```bash
   aws s3 cp tests/fixtures/real_transcripts/<file>.pdf \
     s3://<BucketName>/uploads/<applicationId>/transcript.pdf
   ```

4. **Watch the pipeline** — In CloudWatch Logs, confirm the pipeline
   executes in order:
   - Intake (S3 event trigger)
   - Extract (Bedrock Nova invocation per page)
   - Aggregate (merge per-page JSON)
   - Validate (rule engine)
   - QueueForReview (status update)

5. **Confirm Step Functions success** — In the Step Functions console,
   verify the execution ends in the `SUCCESS` state.

6. **Test the API** — Authenticate as `reviewer1` via Cognito
   (AWS CLI or Hosted UI) and capture the ID token:
   ```bash
   curl -H "Authorization: Bearer <token>" <ApiUrl>/applications
   ```
   Confirm the test application appears in the queue.

   Then hit the detail endpoint:
   ```bash
   curl -H "Authorization: Bearer <token>" <ApiUrl>/applications/<id>
   ```
   Confirm flags are populated.

7. **Check costs** — 24 hours after deploy, check AWS Cost Explorer.
   Daily cost should be under $1 for a single test transcript.

## Teardown

```bash
cdk destroy
```

After `cdk destroy` completes:

1. **Empty and delete the S3 bucket** — CDK will not delete non-empty
   buckets (removal policy is RETAIN). Manually empty and delete:
   ```bash
   aws s3 rm s3://<BucketName> --recursive
   aws s3 rb s3://<BucketName>
   ```

2. **Delete residual log groups** — If CloudWatch log groups did not
   come down with the stack, delete them manually in the console or via:
   ```bash
   aws logs delete-log-group --log-group-name /aws/lambda/msbn-intake
   aws logs delete-log-group --log-group-name /aws/lambda/msbn-extract
   aws logs delete-log-group --log-group-name /aws/lambda/msbn-aggregate
   aws logs delete-log-group --log-group-name /aws/lambda/msbn-validate
   aws logs delete-log-group --log-group-name /aws/lambda/msbn-queue-for-review
   aws logs delete-log-group --log-group-name /aws/lambda/msbn-dashboard-api
   ```

3. **Keep the budget** — The manual `Total_Budget` resource stays in
   the AWS Console. Do not delete it between deploys.
