########################################
# VPC
########################################

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-igw"
  })
}

########################################
# Public subnets — ALB, NAT Gateways only.
# map_public_ip_on_launch is fine here: nothing except the ALB and NAT
# Gateway ENIs live in these subnets, both of which are meant to be
# internet-reachable.
########################################

resource "aws_subnet" "public" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-public-${var.azs[count.index]}"
    Tier = "public"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-public-rt"
  })
}

resource "aws_route_table_association" "public" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

########################################
# Private application subnets — ECS Fargate tasks. Outbound internet access
# (for pulling images, calling the Anthropic/Voyage AI APIs) goes through
# the NAT Gateway(s) below, gated by var.nat_strategy.
########################################

resource "aws_subnet" "app" {
  count             = length(var.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.app_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-app-${var.azs[count.index]}"
    Tier = "private-app"
  })
}

########################################
# Private data subnets — RDS, ElastiCache, MSK. No route to the internet at
# all (not even via NAT): these subnets' route tables only ever get the
# implicit local VPC route. Reachable only from the app subnets, and only
# on the specific ports each security group allows.
########################################

resource "aws_subnet" "data" {
  count             = length(var.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.data_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-data-${var.azs[count.index]}"
    Tier = "private-data"
  })
}

resource "aws_route_table" "data" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-data-rt"
  })
}

resource "aws_route_table_association" "data" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.data[count.index].id
  route_table_id = aws_route_table.data.id
}

########################################
# NAT Gateway(s) — count/placement controlled by var.nat_strategy.
# Each NAT Gateway needs its own Elastic IP, which (since Feb 2024) carries
# its own small hourly charge in addition to the NAT Gateway's own hourly +
# per-GB data processing charge. See README "Cost considerations".
########################################

locals {
  nat_count = var.nat_strategy == "none" ? 0 : (var.nat_strategy == "one_per_az" ? length(var.azs) : 1)
}

resource "aws_eip" "nat" {
  count  = local.nat_count
  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-nat-eip-${count.index}"
  })

  depends_on = [aws_internet_gateway.main]
}

resource "aws_nat_gateway" "main" {
  count         = local.nat_count
  allocation_id = aws_eip.nat[count.index].id
  # "single" strategy: the one NAT Gateway lives in the first public subnet.
  # "one_per_az": one NAT Gateway per public subnet (index-aligned with AZs).
  subnet_id = aws_subnet.public[count.index].id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-nat-${count.index}"
  })

  depends_on = [aws_internet_gateway.main]
}

# One route table per AZ so "one_per_az" can route each AZ's app subnet to
# its own NAT Gateway. Under "single", every app route table points at the
# same (only) NAT Gateway; under "none", no default route is created at all.
resource "aws_route_table" "app" {
  count  = length(var.azs)
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-app-rt-${var.azs[count.index]}"
  })
}

resource "aws_route" "app_nat" {
  count                  = var.nat_strategy == "none" ? 0 : length(var.azs)
  route_table_id         = aws_route_table.app[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = var.nat_strategy == "one_per_az" ? aws_nat_gateway.main[count.index].id : aws_nat_gateway.main[0].id
}

resource "aws_route_table_association" "app" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.app[count.index].id
  route_table_id = aws_route_table.app[count.index].id
}
