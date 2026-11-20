"""BBC Wine data model.

Inventory is always counted in bottles. A case is only a display unit
derived from `Wine.bottles_per_case`. Every change of stock is written to
`StockMovement`, so the stock of any wine at any location can be explained.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Functions that can be granted to a user, in menu order.
FUNCTIONS = {
    "inventory": "Availability & Inventory",
    "customers": "Customers & Purchases",
    "wine_lists": "Customer Wine Lists",
    "orders": "Orders",
    "invoices": "Invoices & QBO Export",
}
LEVEL_VIEW = "view"
LEVEL_USER = "user"
LEVELS = {LEVEL_VIEW: "View", LEVEL_USER: "User"}

CATEGORIES = {"RED": "Red", "WHITE": "White", "ROSE": "Rosé"}
STYLES = {"STILL": "Still", "FRIZZANTE": "Frizzante", "SPARKLING": "Sparkling"}
AVAILABILITIES = {"AVAILABLE": "Available", "INCOMING": "Incoming", "UNAVAILABLE": "Not available"}

ORDER_OPEN = "OPEN"
ORDER_CANCELLED = "CANCELLED"
DISCOUNT_PERCENT = "PCT"
DISCOUNT_AMOUNT = "AMT"

MOVE_ORDER = "ORDER"
MOVE_ORDER_CHANGE = "ORDER_CHANGE"
MOVE_ORDER_CANCEL = "ORDER_CANCEL"
MOVE_ADJUSTMENT = "ADJUSTMENT"
MOVE_LABELS = {MOVE_ORDER: "Order", MOVE_ORDER_CHANGE: "Order changed", MOVE_ORDER_CANCEL: "Order cancelled",
               MOVE_ADJUSTMENT: "Manual adjustment"}


class Company(Base):
    """The distributor's own data, printed on invoices and wine lists (one row)."""
    __tablename__ = "company"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(160))
    license_number: Mapped[str | None] = mapped_column(String(60))
    payment_instructions: Mapped[str | None] = mapped_column(Text)
    invoice_terms_text: Mapped[str | None] = mapped_column(Text)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_rep: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    permissions: Mapped[list["Permission"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def level(self, function: str) -> str | None:
        """The level granted for a function: 'user', 'view' or None."""
        if self.is_admin:
            return LEVEL_USER
        for p in self.permissions:
            if p.function == function:
                return p.level
        return None


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("user_id", "function"),
                      CheckConstraint("level IN ('view', 'user')", name="ck_permission_level"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    function: Mapped[str] = mapped_column(String(40), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    user: Mapped[User] = relationship(back_populates="permissions")


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Wine(Base):
    """A wine BBC sells. `price` is the list selling price per bottle."""
    __tablename__ = "wines"
    __table_args__ = (CheckConstraint("bottles_per_case IS NULL OR bottles_per_case > 0", name="ck_wine_case"),
                      CheckConstraint("price IS NULL OR price >= 0", name="ck_wine_price"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    type_name: Mapped[str] = mapped_column(String(120), nullable=False)
    producer: Mapped[str] = mapped_column(String(160), nullable=False)
    label_name: Mapped[str | None] = mapped_column(String(200))
    vintage_year: Mapped[int | None] = mapped_column(Integer)  # NULL = non-vintage
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    style: Mapped[str] = mapped_column(String(16), nullable=False)
    denomination: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(80))
    bottle_size_ml: Mapped[int] = mapped_column(Integer, nullable=False, default=750)
    bottles_per_case: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    availability: Mapped[str] = mapped_column(String(16), nullable=False, default="AVAILABLE")
    notes: Mapped[str | None] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(String(60))  # where the row was copied from
    stocks: Mapped[list["Stock"]] = relationship(back_populates="wine")

    @property
    def vintage_label(self) -> str:
        return str(self.vintage_year) if self.vintage_year else "NV"

    @property
    def display_name(self) -> str:
        parts = [self.type_name, self.producer]
        if self.label_name:
            parts.append(self.label_name)
        parts.append(self.vintage_label)
        return " - ".join(parts)

    def stock_at(self, location_id: int) -> int:
        return next((s.bottles for s in self.stocks if s.location_id == location_id), 0)

    @property
    def total_stock(self) -> int:
        return sum(s.bottles for s in self.stocks)


class Stock(Base):
    __tablename__ = "stock"
    __table_args__ = (UniqueConstraint("wine_id", "location_id"),
                      CheckConstraint("bottles >= 0", name="ck_stock_not_negative"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bottles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wine: Mapped[Wine] = relationship(back_populates="stocks")
    location: Mapped[Location] = relationship()


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.id"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bottles: Mapped[int] = mapped_column(Integer, nullable=False)  # + in, - out
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    wine: Mapped[Wine] = relationship()
    location: Mapped[Location] = relationship()
    user: Mapped[User | None] = relationship()


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    bill_to: Mapped[str | None] = mapped_column(Text)
    ship_to: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(160))
    license_number: Mapped[str | None] = mapped_column(String(60))
    terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    rep_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rep: Mapped[User | None] = relationship()


class WineList(Base):
    __tablename__ = "wine_lists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    notes: Mapped[str | None] = mapped_column(Text)
    customer: Mapped[Customer] = relationship()
    items: Mapped[list["WineListItem"]] = relationship(back_populates="wine_list", cascade="all, delete-orphan")


class WineListItem(Base):
    __tablename__ = "wine_list_items"
    __table_args__ = (UniqueConstraint("wine_list_id", "wine_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wine_list_id: Mapped[int] = mapped_column(ForeignKey("wine_lists.id"), nullable=False)
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.id"), nullable=False)
    wine_list: Mapped[WineList] = relationship(back_populates="items")
    wine: Mapped[Wine] = relationship()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("discount_value >= 0", name="ck_order_discount"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # also the invoice number in this trial
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    rep_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # NULL = HOUSE
    po_number: Mapped[str | None] = mapped_column(String(60))
    ship_via: Mapped[str | None] = mapped_column(String(60))
    terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=ORDER_OPEN)
    discount_type: Mapped[str] = mapped_column(String(3), nullable=False, default=DISCOUNT_PERCENT)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    customer: Mapped[Customer] = relationship()
    rep: Mapped[User | None] = relationship(foreign_keys=[rep_user_id])
    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan",
                                                    order_by="OrderLine.position")


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (CheckConstraint("bottles > 0", name="ck_line_bottles"),
                      CheckConstraint("discount_value >= 0", name="ck_line_discount"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wine_id: Mapped[int] = mapped_column(ForeignKey("wines.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    bottles: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(3), nullable=False, default=DISCOUNT_PERCENT)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    # Snapshot of what was sold, so later catalog edits do not rewrite an invoice.
    item_code: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(String(400), nullable=False)
    bottles_per_case: Mapped[int | None] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="lines")
    wine: Mapped[Wine] = relationship()
    location: Mapped[Location] = relationship()
