from pydantic import BaseModel, Field, ConfigDict
from typing import Optional,Any

class Letter_Of_Guarantee_Format(BaseModel):
    beneficiary: Optional[str] = Field(None, description="受益人")
    the_guaranteed: Optional[str] = Field(None, description="被保证人")
    types_of_guarantee: Optional[str] = Field(None, description="保函品种")
    number: Optional[str] = Field(None, description="保函编号")
    project_name: Optional[str] = Field(None, description="项目名称")
    guarantee_amount: Optional[str] = Field(None, description="担保金额")
    bank: Optional[str] = Field(None, description="开函银行")