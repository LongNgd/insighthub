# InsightHub EKS module

Creates the Day 3 EKS control plane, encrypted Kubernetes secret storage, a
private managed node group, and an IAM OIDC provider for IRSA. Control-plane
logging is enabled for all supported log types.

The Kubernetes API always has private access. Public access is disabled unless
restricted operator or CI CIDRs are supplied; `0.0.0.0/0` is rejected by the
root module. Nodes run only in private subnets and use encrypted GP3 root disks
with IMDSv2 required.
