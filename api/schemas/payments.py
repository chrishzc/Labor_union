from typing import Optional
from pydantic import BaseModel, Field
from datetime import date

class PaymentUpdateRequest(BaseModel):
    amount_receivable: float = Field(0.0, description="應收金額")
    deposit_received: float = Field(0.0, description="已收訂金")
    balance_received: float = Field(0.0, description="已收尾款")
    caregiver_fee: float = Field(0.0, description="應付月嫂費用")
    payment_status: str = Field("待收訂金", description="帳務狀態")
    notes: Optional[str] = Field(None, description="帳務備註")
    deposit_received_at: Optional[date] = Field(None, description="訂金入帳日")
    balance_received_at: Optional[date] = Field(None, description="尾款入帳日")
    caregiver_paid_at: Optional[date] = Field(None, description="月嫂轉帳日")
