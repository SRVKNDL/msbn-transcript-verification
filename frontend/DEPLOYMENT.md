# Frontend Deployment Notes

The dashboard frontend is currently hosted outside CDK using a manually created
S3 bucket and CloudFront distribution.

Current frontend hosting resources:

- S3 bucket: `msbn-dashboard-frontend-357621881714`
- CloudFront distribution: `EWFC9ZR5VW20B`
- CloudFront origin access control: `E11XHVY91JWC6H`

The JSON files in this directory are resource snapshots for this AWS account:

- `bucket-policy.json`
- `cloudfront-config.json`

Do not apply those JSON files to another AWS account as-is. They contain
account-specific ARNs and resource IDs.

For a frontend redeploy, build and sync the generated `dist/` directory:

```bash
npm run build
aws s3 sync dist/ s3://msbn-dashboard-frontend-357621881714/ --delete
aws cloudfront create-invalidation --distribution-id EWFC9ZR5VW20B --paths "/*"
```

Required build-time environment variables:

```bash
VITE_API_BASE=https://<api-id>.execute-api.us-east-1.amazonaws.com
VITE_COGNITO_CLIENT_ID=<user-pool-client-id>
VITE_COGNITO_REGION=us-east-1
```
