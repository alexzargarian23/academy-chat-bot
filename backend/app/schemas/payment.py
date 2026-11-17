
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PaymentMethod = Literal[
    "cash",
    "bank_transfer",
    "card",
    "other"
]


class InvoiceCreate(BaseModel):
    student_profile_id: int = Field(gt=0)
    description: str = Field(min_length=1)
    academic_year: str = Field(min_length=1, max_length=30)
    total_amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    due_date: date | None = None


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=100)


class PaymentResponse(BaseModel):
    id: int
    invoice_id: int
    amount: Decimal
    method: str
    reference: str | None
    paid_at: datetime
    received_by: int

    model_config = ConfigDict(from_attributes=True)


class InvoiceResponse(BaseModel):
    id: int
    student_profile_id: int
    student_number: str
    student_name: str
    description: str
    academic_year: str
    total_amount: Decimal
    currency: str
    due_date: date | None
    status: str
    paid_amount: Decimal
    balance: Decimal
    created_at: datetime
    payments: list[PaymentResponse] = []

    model_config = ConfigDict(from_attributes=True)
