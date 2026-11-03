# AWS read-only IAM policy

Use [`policies/aws-read-only-policy.json`](../policies/aws-read-only-policy.json) as the starting point for the live AWS connector. It is intentionally read-only and excludes Lambda invocation, code download, updates, deletion, IAM role assumption changes, and all infrastructure mutation.

## Actions

| Action | Why GroundTruth needs it |
| --- | --- |
| `sts:GetCallerIdentity` | Confirm the account context used by the investigation. |
| `lambda:GetFunction` | Read function configuration and ARN. |
| `lambda:GetFunctionEventInvokeConfig` | Read async invoke configuration where present. |
| `lambda:GetFunctionUrlConfig` | Read function URL context where present. |
| `lambda:ListAliases` | Read alias/version context. |
| `lambda:ListEventSourceMappings` | Read trigger/dependency context. |
| `lambda:ListFunctions` | Populate read-only resource inventory. |
| `lambda:ListTags` | Read resource tags as candidate context. |
| `iam:GetRole` | Read execution-role metadata, not policy contents. |
| `cloudtrail:LookupEvents` | Read regional management-event history. |
| `cloudwatch:GetMetricData` | Read invocation/error/duration datapoints. |
| `cloudwatch:ListMetrics` | Verify Lambda metric availability. |

`lambda:GetFunction` can return a code download URL. GroundTruth does not retain or export it. Environment-variable values are not collected in evidence.

## Attach the policy

1. Create a read-only role in the target account, preferably through IAM Identity Center permission-set or an assumed role.
2. Attach the inline policy from `policies/aws-read-only-policy.json`.
3. Restrict `Resource` further if your resource naming allows it. The reference file uses `"*"` because Lambda list/get operations and CloudTrail Event History are not cleanly scoped to one ARN.
4. Configure `AWS_PROFILE` or the standard credential chain locally. Do not put access keys in `.env`.
5. Open **Settings / connections** and run the AWS connection test. A configured profile is not a successful test.

Example profile check:

```bash
aws sts get-caller-identity --profile groundtruth-ro
aws lambda get-function --function-name orders-transformer --region ap-south-1 --profile groundtruth-ro
```

If the test returns `permission_denied`, the UI reports that status and the engine will not turn it into "no resources found." If the test returns `not_configured`, check `AWS_PROFILE`, `AWS_REGION`, and the local credential chain.

## CloudTrail and CloudWatch scope

- CloudTrail Event History covers regional management events for up to 90 days. It does not provide data events by default and does not prove intent.
- CloudWatch reads are limited to the configured lookback/period and Lambda namespace.
- Use separate roles/profiles per account where possible; do not use a broad administrator role for convenience.
- AWS Organizations SCPs may further restrict `LookupEvents` or `GetMetricData`.

## Revocation

Remove the policy attachment or disable the role when the demo is complete. Revoke any temporary credentials used for testing. Do not commit profiles, access keys, session tokens, or SSO caches.
