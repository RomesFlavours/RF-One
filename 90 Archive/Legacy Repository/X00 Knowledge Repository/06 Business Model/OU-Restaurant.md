# Restaurant

**Document Version:** 2.1
**Status:** Approved
**Module:** Core Domain
**Extends:** Operational Unit

---

# Definition

A **Restaurant** is a specialization of an Operational Unit whose primary purpose is to prepare, produce and serve food and beverages.

It combines food production, hospitality and customer service within a single operational environment.

A Restaurant inherits all Operational Unit capabilities while introducing restaurant-specific concepts.

---

# Purpose

The Restaurant transforms:

- Ingredients
- Recipes
- Employees
- Equipment
- Facilities

into Products and Services delivered to customers.

---

# Position in the Domain

```
Corporate
    ↓
Brand
    ↓
Operational Unit
    ↓
Restaurant
```

Restaurant inherits every capability of Operational Unit and extends it with restaurant-specific behavior.

---

# Inherited Capabilities

A Restaurant inherits:

- Identity
- Operational Boundary
- Legal Identity
- Employees
- Operational Areas
- Equipment
- Inventory
- Processes
- Services
- Availability
- Capacity

---

# Restaurant Characteristics

Typical components include:

- Dining Areas
- Kitchen
- Bar
- Storage
- Customer Seating
- Food Production
- Beverage Production
- Customer Service

The exact configuration depends on the business model.

---

# Operational Areas

Typical areas include:

- Kitchen
- Bar
- Dining Room
- Patio
- Storage
- Office
- Receiving Area
- Restrooms

Additional Operational Areas may be added without changing the model.

---

# Products

Restaurants produce and/or serve Products such as:

- Food
- Beverages
- Wine
- Cocktails
- Desserts
- Merchandise

Products remain independent business entities.

---

# Recipes

Recipes define:

- Ingredients
- Preparation
- Portions
- Production Standards

Restaurants execute Recipes.

---

# Services

Typical Services include:

- Dine-In
- Take-Out
- Delivery
- Catering
- Private Events
- Online Ordering

Services are independent entities delivered by the Restaurant.

---

# Hospitality

Restaurants provide experiences including:

- Guest Reception
- Table Service
- Customer Assistance
- Dining Experience
- Complaint Resolution

Hospitality standards are defined by the Brand.

---

# Capacity

Capacity may include:

- Indoor Seating
- Outdoor Seating
- Bar Seating
- Private Rooms

---

# Availability

Availability depends on:

- Operating Hours
- Staff Availability
- Equipment Availability
- Operational Areas
- Regulatory Constraints

Availability follows RF-ONE Domain Principles.

---

# Relationships

A Restaurant may relate to:

- Brand
- Corporate
- Operational Areas
- Employees
- Customers
- Orders
- Products
- Recipes
- Ingredients
- Inventory
- Equipment
- Suppliers
- Reservations
- Menus
- Services
- Documents

Relationships never define identity.

---

# Business Rules

- Restaurant extends Operational Unit.
- Every Restaurant belongs to one Operational Unit.
- Every Restaurant belongs to one Brand.
- Every Restaurant belongs to one Corporate.
- Restaurants prepare and/or serve Products.
- Recipes define preparation.
- Products and Services remain independent entities.
- Operational Areas belong to the Restaurant.
- Hospitality standards are defined by the Brand.
- Restaurant identity is immutable.

---

# Future Scalability

The Restaurant model supports:

- Fine Dining
- Casual Dining
- Fast Casual
- Quick Service
- Café
- Wine Bar
- Bakery
- Pizzeria
- Ghost Kitchen
- Food Hall
- Buffet
- Hybrid Concepts

without requiring changes to the RF-ONE Core Domain.
