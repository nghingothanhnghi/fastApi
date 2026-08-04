# app/cms/schemas/menu.py
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime

from app.cms.models.menu import MenuItemTargetType


class MenuItemBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=150)
    target_type: MenuItemTargetType = MenuItemTargetType.custom
    url: Optional[str] = Field(None, max_length=500)
    target_id: Optional[int] = None
    parent_id: Optional[int] = None
    order: int = 0
    open_in_new_tab: bool = False
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_target(self):
        if self.target_type == MenuItemTargetType.custom and not self.url:
            raise ValueError("url is required when target_type is 'custom'")
        if self.target_type in (MenuItemTargetType.category, MenuItemTargetType.post) and not self.target_id:
            raise ValueError("target_id is required when target_type is 'category' or 'post'")
        return self


class MenuItemCreate(MenuItemBase):
    pass


class MenuItemUpdate(BaseModel):
    label: Optional[str] = None
    target_type: Optional[MenuItemTargetType] = None
    url: Optional[str] = None
    target_id: Optional[int] = None
    parent_id: Optional[int] = None
    order: Optional[int] = None
    open_in_new_tab: Optional[bool] = None
    is_active: Optional[bool] = None


class MenuItemOut(MenuItemBase):
    id: int
    menu_id: int
    resolved_url: Optional[str] = None  # filled in by the service, not the DB
    children: List["MenuItemOut"] = []

    model_config = {"from_attributes": True}


MenuItemOut.model_rebuild()


class MenuBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    location: Optional[str] = Field(None, max_length=50)


class MenuCreate(MenuBase):
    slug: Optional[str] = Field(None, description="Auto-generated from name if omitted")


class MenuUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    location: Optional[str] = None


class MenuOut(MenuBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    items: List[MenuItemOut] = []  # nested tree, built by the service

    model_config = {"from_attributes": True}


# Reordering payload: flat list of {id, parent_id, order} updates in one call
class MenuItemReorderEntry(BaseModel):
    id: int
    parent_id: Optional[int] = None
    order: int


class MenuReorderRequest(BaseModel):
    items: List[MenuItemReorderEntry]