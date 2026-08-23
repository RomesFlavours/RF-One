# Operational Unit

**Document Version:** 4.0 **Status:** Approved **Module:** Core Domain

------------------------------------------------------------------------

# Definition

An **Operational Unit (OU)** is the fundamental operational entity
within RF-ONE.

It defines the operational boundary inside which business activities are
executed and operational resources are managed.

Every operational activity, employee, operational asset, inventory item,
process, capability and operational responsibility is assigned to
exactly one Operational Unit.

An Operational Unit may generate revenue, incur costs, provide services
or support other Operational Units.

A Restaurant is one specialization of an Operational Unit.

------------------------------------------------------------------------

# Purpose

Operational Units exist to execute the business strategy defined by the
Corporate and the customer experience defined by the Brand.

They transform business resources into operational results.

Depending on their specialization, an Operational Unit may:

-   Generate revenue
-   Produce goods
-   Deliver services
-   Support other Operational Units
-   Manage operational resources
-   Coordinate business processes
-   Operate physical facilities

Operational Units are the primary building blocks from which every
business operation is modeled.

------------------------------------------------------------------------

# Responsibility

Operational Units are responsible for operational execution.

They coordinate business resources, execute business Processes and
deliver business Services.

Operational responsibilities may be delegated to Operational Areas
without changing the Operational Unit's overall responsibility.

Operational Units never define corporate strategy or brand standards.

------------------------------------------------------------------------

# Position in the Domain

``` text
Corporate
    ↓
Brand
    ↓
Operational Unit
    ↓
Operational Area
```

Every operational entity ultimately belongs to an Operational Unit.

------------------------------------------------------------------------

# Operational Boundary

An Operational Unit defines the boundary within which operational
responsibilities are managed.

Every operational resource and operational activity within that boundary
is assigned to exactly one Operational Unit.

This includes:

-   Employees
-   Operational Areas
-   Equipment
-   Inventory
-   Products
-   Processes
-   Documents
-   Customers
-   Suppliers
-   Services
-   Operational Assets

The Operational Unit is the primary operational responsibility boundary
for business execution.

------------------------------------------------------------------------

# Relationship with Corporate

Every Operational Unit belongs to exactly one Corporate.

The Corporate owns the Operational Unit and defines its strategic
direction.

Corporate retains ownership and governance.

Operational Units retain operational responsibility.

------------------------------------------------------------------------

# Relationship with Brand

Every Operational Unit belongs to exactly one Brand.

The Brand defines:

-   Customer Experience
-   Commercial Identity
-   Service Standards
-   Product Standards

The Brand defines what customers should experience.

The Operational Unit defines how that experience is operationally
delivered.

------------------------------------------------------------------------

# Physical Location

Every Operational Unit represents exactly one physical location.

Multiple physical locations always require multiple Operational Units.

This principle guarantees clear assignment of:

-   Employees
-   Operational Assets
-   Inventory
-   Capacity
-   Availability
-   Operational Responsibilities

------------------------------------------------------------------------

# Identity

Every Operational Unit owns a unique RF-ONE identifier.

Its identity is immutable.

The following attributes may change without creating a new Operational
Unit:

-   Name
-   Address
-   Manager
-   Operating Hours
-   Business Model

------------------------------------------------------------------------

# Legal Identity

An Operational Unit may possess legal identity when required by the
organization's legal structure or local regulations.

Typical legal attributes include:

-   Legal Name
-   Legal Entity Type
-   Registration Number
-   Tax Identification Number
-   Business Licenses

Specialization-specific legal information belongs to the specialization.

------------------------------------------------------------------------

# Lifecycle

Planning

↓

Legal Creation

↓

Site Acquisition

↓

Construction / Setup

↓

Licensing

↓

Operational

↓

Temporarily Closed (optional)

↓

Permanently Closed

The Operational Unit exists as soon as it has been legally established,
even before becoming operational.

------------------------------------------------------------------------

# Known Specializations

-   Restaurant
-   Warehouse
-   Central Kitchen
-   Production Facility
-   Retail Store
-   Food Truck
-   Import Company
-   Marketing Agency
-   Administrative Office
-   Distribution Center

Additional specializations may be introduced without modifying the Core
Domain.

------------------------------------------------------------------------

# Operational Areas

Every Operational Unit contains one or more Operational Areas.

Operational Areas partition operational responsibilities inside the
Operational Unit.

Operational Areas never exist independently.

------------------------------------------------------------------------

# Services

Operational Units may provide one or more Services.

Services are independent business entities.

Operational Units execute Services.

------------------------------------------------------------------------

# Capabilities

Capabilities describe what an Operational Unit is able to perform.

Capabilities enable one or more Services.

------------------------------------------------------------------------

# Capacity

Operational Units own or aggregate operational capacities.

Capacity belongs to the physical provider.

Higher organizational levels may aggregate capacities.

------------------------------------------------------------------------

# Availability

Operational Units define their operational availability.

Availability is derived from subordinate entities according to business
rules.

------------------------------------------------------------------------

# Relationships

Operational Units may be related to:

-   Corporate
-   Brand
-   Operational Areas
-   Employees
-   Products
-   Recipes
-   Equipment
-   Inventory
-   Customers
-   Suppliers
-   Services
-   Processes
-   Documents
-   Other Operational Units

Relationships never define Operational Unit identity.

------------------------------------------------------------------------

# Business Rules

-   Every Operational Unit belongs to exactly one Corporate.
-   Every Operational Unit belongs to exactly one Brand.
-   Every Operational Unit represents exactly one physical location.
-   Every Operational Unit defines an operational boundary.
-   Every operational resource is assigned to exactly one Operational
    Unit.
-   Operational responsibility belongs to the Operational Unit.
-   Operational responsibilities may be delegated to Operational Areas.
-   Corporate owns Operational Units without performing operational
    execution.
-   Restaurant is a specialization of Operational Unit.
-   Specialized entities extend Operational Unit rather than replacing
    it.
-   Capabilities enable Services.
-   Capacity belongs to the physical provider.
-   Availability belongs to the smallest responsible entity.
-   Relationships never define Operational Unit identity.

------------------------------------------------------------------------

# Future Scalability

The Operational Unit model is intentionally industry-independent.

It supports hospitality, retail, logistics, manufacturing,
administrative organizations and future business models without
requiring modifications to the RF-ONE Core Domain.