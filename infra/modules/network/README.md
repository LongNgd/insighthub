# InsightHub network module

Creates a dedicated VPC across two Availability Zones with two public subnets,
two private subnets, an Internet Gateway, and one lab-sized NAT Gateway. EKS
nodes, RDS, and Redis use only the private subnets. The public subnets are for
the NAT Gateway and future internet-facing load balancers.

One NAT Gateway is a deliberate lab cost tradeoff and is not an HA production
topology. VPC Flow Logs are sent to CloudWatch Logs, and the default security
group has no ingress or egress rules.
