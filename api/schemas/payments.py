from typing import Optional
from pydantic import BaseModel, Field
from datetime import date

class PaymentUpdateRequest(BaseModel):
    deposit_receivable: float = Field(0.0, description="訂金應收金額")
    deposit_received: float = Field(0.0, description="訂金實收金額")
    deposit_due_date: Optional[date] = Field(None, description="訂金應收日期")
    deposit_received_at: Optional[date] = Field(None, description="訂金實收日期")
    first_payment_receivable: float = Field(0.0, description="第一期應收金額")
    first_payment_received: float = Field(0.0, description="第一期實收金額")
    first_payment_due_date: Optional[date] = Field(None, description="第一期應收日期")
    first_payment_received_at: Optional[date] = Field(None, description="第一期實收日期")
    second_payment_receivable: float = Field(0.0, description="第二期應收金額")
    second_payment_received: float = Field(0.0, description="第二期實收金額")
    second_payment_due_date: Optional[date] = Field(None, description="第二期應收日期")
    second_payment_received_at: Optional[date] = Field(None, description="第二期實收日期")
    caregiver_fee: float = Field(0.0, description="應付月嫂費用")
    payment_status: str = Field("待收訂金", description="帳務狀態")
    notes: Optional[str] = Field(None, description="帳務備註")
    caregiver_paid_at: Optional[date] = Field(None, description="月嫂轉帳日")
