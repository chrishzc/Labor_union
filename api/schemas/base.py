from typing import Annotated, Generic, TypeVar, Optional, Any
from pydantic import BaseModel, PlainSerializer

T = TypeVar("T")

ExactNtd = Annotated[int, PlainSerializer(
    lambda amount: amount if abs(amount) <= 9_007_199_254_740_991 else str(amount),
    return_type=int | str, when_used="json",
)]

class BaseResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "Success"
    data: Optional[T] = None
    error: Optional[str] = None
