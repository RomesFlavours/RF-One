# Product

## Purpose

A Product represents the generic culinary concept shared by one or more Ingredients.

It is an abstract business entity that identifies what the ingredient is, independently of its origin, quality, specifications, supplier or commercial characteristics.

Products provide the common vocabulary used throughout the Restaurant Domain.

---

# Business Meaning

A Product identifies the generic food concept.

Examples:

- Tomato
- Olive Oil
- Parmesan Cheese
- Flour
- Mozzarella
- Basil

A Product is not sufficiently detailed to be used directly in Recipes or Purchasing.

Recipes always use Ingredients.

Purchasing always uses Supplier Products.

---

# Product Identity

A Product is identified only by its canonical business name.

Commercial names, brands and supplier terminology are never part of the Product identity.

---

# Responsibilities

- Provide the generic culinary concept.
- Group equivalent Ingredients.
- Support business classification.
- Provide a stable business vocabulary.

---

# Relationships

A Product:

- may define many Specifications;
- may generate many Ingredients;
- may be referenced by many Supplier Products through their Ingredients.

Relationship:

Product
↓
Specifications
↓
Ingredient
↓
Supplier Product

---

# Specifications

A Product becomes a specific Ingredient through one or more Specifications.

Each different combination identifies a different Ingredient.

---

# Purchasing

Products are never purchased directly.

Purchasing references Supplier Products.

Supplier Products are mapped to Ingredients.

Ingredients reference Products.

---

# Recipes

Recipes never reference Products directly.

Recipes always reference Ingredients.

---

# Artificial Intelligence

AI may:

- recognize Products from Supplier Products;
- suggest Product classifications;
- detect possible Product inconsistencies.

AI never creates Products autonomously.

---

# Design Principles

- A Product represents a generic culinary concept.
- Products are supplier independent.
- Products are specification independent.
- Products are never purchased directly.
- Products are never used directly in Recipes.
- Ingredients specialize Products through Specifications.
- Products provide the canonical business vocabulary of the Restaurant Domain.
