"""Private Internet egress for the RF-One App Runner services.

Problem: every App Runner service leaves through the VPC connector
`rfone-tips-vpc-connector`, whose subnets have no NAT. App Runner connector
interfaces never get a public IP, so the default VPC's `0.0.0.0/0 -> igw`
route does nothing for them: from production no external server is
reachable (Aruba SMTP, the Anthropic API, SES...). Only S3, ECS and Bedrock
work, through VPC endpoints.

Solution (built here, idempotent, every resource tagged `rfone:purpose=private-egress`):
  - one managed NAT gateway + Elastic IP in an existing public subnet (us-east-1a);
  - two NEW private subnets (172.31.96.0/20 in 1a, 172.31.112.0/20 in 1b) with
    their own route table `0.0.0.0/0 -> NAT`, also attached to the existing S3
    gateway endpoint (S3 traffic stays free and off the NAT);
  - a NEW VPC connector `rfone-private-egress` on those subnets with the same
    security group as today's connector;
  - only the services named on the command line are moved to it.
The existing subnets, their route table, the RDS instances and the old
connector are NOT touched — public access to `rfone-dev` keeps working, and
rollback is moving a service back to the old connector.

    python private_egress.py plan                        read-only checks (default)
    python private_egress.py apply --services rfone-selection rfone-selection-ai-test
    python private_egress.py rollback --services rfone-selection rfone-selection-ai-test
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
import time

import boto3

REGION = "us-east-1"
OLD_CONNECTOR_NAME = "rfone-tips-vpc-connector"
NEW_CONNECTOR_NAME = "rfone-private-egress"
NAT_PUBLIC_SUBNET = "subnet-088592c1a293b4e20"  # us-east-1a, default public subnet
PRIVATE_SUBNETS = {"us-east-1a": "172.31.96.0/20", "us-east-1b": "172.31.112.0/20"}
TAG = {"Key": "rfone:purpose", "Value": "private-egress"}

ec2 = boto3.client("ec2", region_name=REGION)
apprunner = boto3.client("apprunner", region_name=REGION)


def _tags(name: str) -> list[dict]:
    return [{"ResourceType": "", "Tags": [TAG, {"Key": "Name", "Value": name}]}]


def _spec(resource_type: str, name: str) -> list[dict]:
    spec = _tags(name)
    spec[0]["ResourceType"] = resource_type
    return spec


def _tagged(describe, key: str, **filters) -> list[dict]:
    flt = [{"Name": "tag:rfone:purpose", "Values": ["private-egress"]}]
    flt += [{"Name": k, "Values": v} for k, v in filters.items()]
    return describe(Filters=flt)[key]


def _our_nat_gateways() -> list[dict]:
    return ec2.describe_nat_gateways(Filter=[{"Name": "tag:rfone:purpose", "Values": ["private-egress"]},
                                             {"Name": "state", "Values": ["available", "pending"]}])["NatGateways"]


def _connector_name(arn: str) -> str:
    return arn.split(":vpcconnector/", 1)[1].split("/", 1)[0]


def old_connector() -> dict:
    found = [c for c in apprunner.list_vpc_connectors()["VpcConnectors"]
             if c["VpcConnectorName"] == OLD_CONNECTOR_NAME and c["Status"] == "ACTIVE"]
    if not found:
        sys.exit(f"Connector {OLD_CONNECTOR_NAME} not found.")
    return found[0]


def new_connector() -> dict | None:
    found = [c for c in apprunner.list_vpc_connectors()["VpcConnectors"]
             if c["VpcConnectorName"] == NEW_CONNECTOR_NAME and c["Status"] == "ACTIVE"]
    return found[0] if found else None


def service_arn(name: str) -> str:
    for s in apprunner.list_services()["ServiceSummaryList"]:
        if s["ServiceName"] == name:
            return s["ServiceArn"]
    sys.exit(f"App Runner service {name} not found.")


def plan(_args) -> None:
    old = old_connector()
    subnet = ec2.describe_subnets(SubnetIds=[NAT_PUBLIC_SUBNET])["Subnets"][0]
    vpc_id = subnet["VpcId"]
    vpc = ec2.describe_vpcs(VpcIds=[vpc_id])["Vpcs"][0]
    existing = [s["CidrBlock"] for s in ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]]
    print(f"VPC {vpc_id} {vpc['CidrBlock']}; old connector subnets {old['Subnets']}, SG {old['SecurityGroups']}")
    routes = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]},
                                                {"Name": "association.main", "Values": ["true"]}])["RouteTables"][0]
    igw = any(r.get("GatewayId", "").startswith("igw-") and r.get("DestinationCidrBlock") == "0.0.0.0/0"
              for r in routes["Routes"])
    ok = True
    print(f"  NAT subnet {NAT_PUBLIC_SUBNET} ({subnet['AvailabilityZone']}) is public (igw route): {igw}")
    ok &= igw
    for az, cidr in PRIVATE_SUBNETS.items():
        inside = ipaddress.ip_network(cidr).subnet_of(ipaddress.ip_network(vpc["CidrBlock"]))
        clash = [c for c in existing if ipaddress.ip_network(c).overlaps(ipaddress.ip_network(cidr))]
        mine = _tagged(ec2.describe_subnets, "Subnets", **{"cidr-block": [cidr]})
        print(f"  private subnet {cidr} in {az}: inside VPC {inside}; "
              f"{'already created' if mine else ('FREE' if not clash else 'CONFLICT ' + str(clash))}")
        ok &= inside and (bool(mine) or not clash)
    nats = _our_nat_gateways()
    print(f"  NAT gateway: {'exists ' + nats[0]['NatGatewayId'] if nats else 'to be created'}")
    nc = new_connector()
    print(f"  connector {NEW_CONNECTOR_NAME}: {'exists' if nc else 'to be created'}")
    print("  services and their connector today:")
    for s in apprunner.list_services()["ServiceSummaryList"]:
        cfg = apprunner.describe_service(ServiceArn=s["ServiceArn"])["Service"]["NetworkConfiguration"]["EgressConfiguration"]
        arn = cfg.get("VpcConnectorArn")
        print(f"    {s['ServiceName']}: {_connector_name(arn) if arn else cfg['EgressType']}")
    print("PLAN OK" if ok else "PLAN HAS PROBLEMS")
    if not ok:
        sys.exit(1)


def _wait_nat(nat_id: str) -> None:
    ec2.get_waiter("nat_gateway_available").wait(NatGatewayIds=[nat_id])


def apply(args) -> None:
    old = old_connector()
    vpc_id = ec2.describe_subnets(SubnetIds=[NAT_PUBLIC_SUBNET])["Subnets"][0]["VpcId"]

    nats = _our_nat_gateways()
    if nats:
        nat_id = nats[0]["NatGatewayId"]
    else:
        eip = ec2.allocate_address(Domain="vpc", TagSpecifications=_spec("elastic-ip", "rfone-private-egress-nat"))
        nat_id = ec2.create_nat_gateway(SubnetId=NAT_PUBLIC_SUBNET, AllocationId=eip["AllocationId"],
                                        TagSpecifications=_spec("natgateway", "rfone-private-egress"))["NatGateway"]["NatGatewayId"]
        print(f"NAT gateway {nat_id} created (Elastic IP {eip['PublicIp']}), waiting until available...")
    _wait_nat(nat_id)

    tables = _tagged(ec2.describe_route_tables, "RouteTables", **{"vpc-id": [vpc_id]})
    if tables:
        rtb = tables[0]["RouteTableId"]
    else:
        rtb = ec2.create_route_table(VpcId=vpc_id, TagSpecifications=_spec("route-table", "rfone-private-egress"))[
            "RouteTable"]["RouteTableId"]
        ec2.create_route(RouteTableId=rtb, DestinationCidrBlock="0.0.0.0/0", NatGatewayId=nat_id)
        print(f"Route table {rtb}: 0.0.0.0/0 -> {nat_id}")

    s3 = [e for e in ec2.describe_vpc_endpoints(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["VpcEndpoints"]
          if e["VpcEndpointType"] == "Gateway" and e["ServiceName"].endswith(".s3")]
    if s3 and rtb not in s3[0]["RouteTableIds"]:
        ec2.modify_vpc_endpoint(VpcEndpointId=s3[0]["VpcEndpointId"], AddRouteTableIds=[rtb])
        print(f"S3 gateway endpoint {s3[0]['VpcEndpointId']} attached to {rtb}")

    subnet_ids = []
    for az, cidr in PRIVATE_SUBNETS.items():
        mine = _tagged(ec2.describe_subnets, "Subnets", **{"cidr-block": [cidr]})
        if mine:
            sid = mine[0]["SubnetId"]
        else:
            sid = ec2.create_subnet(VpcId=vpc_id, CidrBlock=cidr, AvailabilityZone=az,
                                    TagSpecifications=_spec("subnet", f"rfone-private-egress-{az}"))["Subnet"]["SubnetId"]
            print(f"Subnet {sid} {cidr} {az} created")
        assoc = ec2.describe_route_tables(Filters=[{"Name": "association.subnet-id", "Values": [sid]}])["RouteTables"]
        if not assoc:
            ec2.associate_route_table(RouteTableId=rtb, SubnetId=sid)
        subnet_ids.append(sid)

    nc = new_connector()
    if not nc:
        nc = apprunner.create_vpc_connector(VpcConnectorName=NEW_CONNECTOR_NAME, Subnets=subnet_ids,
                                            SecurityGroups=old["SecurityGroups"],
                                            Tags=[{"Key": TAG["Key"], "Value": TAG["Value"]}])["VpcConnector"]
        print(f"VPC connector {nc['VpcConnectorArn']} created")
    _move(args.services, nc["VpcConnectorArn"])


def _move(services: list[str], connector_arn: str) -> None:
    for name in services:
        arn = service_arn(name)
        apprunner.update_service(ServiceArn=arn, NetworkConfiguration={
            "EgressConfiguration": {"EgressType": "VPC", "VpcConnectorArn": connector_arn}})
        print(f"{name}: moving to {_connector_name(connector_arn)}...")
        while apprunner.describe_service(ServiceArn=arn)["Service"]["Status"] == "OPERATION_IN_PROGRESS":
            time.sleep(15)
        print(f"{name}: {apprunner.describe_service(ServiceArn=arn)['Service']['Status']}")


def rollback(args) -> None:
    _move(args.services, old_connector()["VpcConnectorArn"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("plan").set_defaults(run=plan)
    for name, fn in (("apply", apply), ("rollback", rollback)):
        p = sub.add_parser(name)
        p.add_argument("--services", nargs="+", required=True)
        p.set_defaults(run=fn)
    args = parser.parse_args()
    getattr(args, "run", plan)(args)


if __name__ == "__main__":
    main()
