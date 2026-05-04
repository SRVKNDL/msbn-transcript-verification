# Frontend Deployment

The frontend is built with Vite and deployed separately from the CDK stacks.

## Preferred Deployment Path

Use the repository deployment helper:

```bash
scripts/deploy.sh frontend \
  --frontend-bucket <bucket-name> \
  --distribution-id <cloudfront-distribution-id>
```

This builds `frontend/dist/`, uploads the assets, and invalidates CloudFront.

## Manual Deployment

If you need to deploy manually:

```bash
cd frontend
npm run build
aws s3 sync dist/ s3://<bucket-name>/ --delete
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

## Required Build-Time Environment Variables

```bash
VITE_API_BASE=https://<api-id>.execute-api.us-east-1.amazonaws.com
VITE_COGNITO_CLIENT_ID=<user-pool-client-id>
VITE_COGNITO_REGION=us-east-1
```

## Notes

- Keep account-specific bucket names, distribution IDs, and snapshots in
  local-only development notes, not committed docs.
- `frontend/dist/` is generated output and should not be committed.
