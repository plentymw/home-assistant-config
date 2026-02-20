"""
Pydantic models for API request/response validation.
These define the structure of data sent to/from the API.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import date


# ============================================================================
# PERSON MODELS
# ============================================================================

class PersonBase(BaseModel):
    name: str

class PersonCreate(PersonBase):
    pass

class Person(PersonBase):
    id: int
    
    class Config:
        from_attributes = True


# ============================================================================
# INGREDIENT MODELS
# ============================================================================

class IngredientBase(BaseModel):
    name: str
    unit: str
    cost_per_unit: float = 0.0
    kcal_per_unit: float = 0.0
    protein_per_unit: float = 0.0
    carbs_per_unit: float = 0.0
    fat_per_unit: float = 0.0
    pack_size: Optional[float] = None
    pack_cost: Optional[float] = None

class IngredientCreate(IngredientBase):
    pass

class IngredientUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    cost_per_unit: Optional[float] = None
    kcal_per_unit: Optional[float] = None
    protein_per_unit: Optional[float] = None
    carbs_per_unit: Optional[float] = None
    fat_per_unit: Optional[float] = None
    pack_size: Optional[float] = None
    pack_cost: Optional[float] = None

class Ingredient(IngredientBase):
    id: int
    
    class Config:
        from_attributes = True


# ============================================================================
# RECIPE MODELS
# ============================================================================

class RecipePortionBase(BaseModel):
    ingredient_id: int
    person_id: int
    quantity: float

class RecipePortionCreate(RecipePortionBase):
    pass

class RecipePortion(RecipePortionBase):
    id: int
    ingredient_name: Optional[str] = None
    person_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class RecipeBase(BaseModel):
    name: str
    meal_type: str  # "breakfast", "lunch", "dinner", "snack"

class RecipeCreate(RecipeBase):
    portions: List[RecipePortionCreate] = []

class Recipe(RecipeBase):
    id: int
    portions: List[RecipePortion] = []
    
    class Config:
        from_attributes = True


# ============================================================================
# WEEK PLAN MODELS
# ============================================================================

class WeekPlanBase(BaseModel):
    date: date
    person_id: int
    meal_type: str  # "breakfast", "lunch", "dinner"
    recipe_id: Optional[int] = None

class WeekPlanCreate(WeekPlanBase):
    pass

class WeekPlanUpdate(BaseModel):
    recipe_id: Optional[int] = None

class WeekPlan(WeekPlanBase):
    id: int
    person_name: Optional[str] = None
    recipe_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# SNACK MODELS
# ============================================================================

class SnackBase(BaseModel):
    name: str
    ingredient_id: int
    default_quantity: float

class SnackCreate(SnackBase):
    pass

class Snack(SnackBase):
    id: int
    
    class Config:
        from_attributes = True


class SnackLogBase(BaseModel):
    date: date
    person_id: int
    snack_id: int
    consumed: bool = False

class SnackLogCreate(SnackLogBase):
    pass

class SnackLogUpdate(BaseModel):
    consumed: bool

class SnackLog(SnackLogBase):
    id: int
    person_name: Optional[str] = None
    snack_name: Optional[str] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# CALCULATION RESPONSE MODELS (What HA will read)
# ============================================================================

class PersonDailyTotals(BaseModel):
    """Daily totals for one person"""
    person: str
    kcal: float
    protein: float
    carbs: float
    fat: float

class PersonWeeklyTotals(BaseModel):
    """Weekly totals for one person"""
    person: str
    kcal: float
    protein: float
    carbs: float
    fat: float

class ShoppingItem(BaseModel):
    """Single item on shopping list"""
    ingredient: str
    quantity: float
    unit: str
    cost: float

class WeekTotalsResponse(BaseModel):
    """Complete weekly summary (what HA sensors will read)"""
    # Today's totals
    today_cost: float
    today_totals: List[PersonDailyTotals]
    
    # Weekly totals
    week_cost: float
    week_totals: List[PersonWeeklyTotals]
    
    # Shopping lists
    wed_shopping: List[ShoppingItem]
    sun_shopping: List[ShoppingItem]
    
    # Metadata
    week_start: date
    last_updated: str


# ============================================================================
# BULK UPDATE MODELS (For HA to write back)
# ============================================================================

class MealSelection(BaseModel):
    """Single meal selection from HA"""
    day: str  # "mon", "tue", etc.
    person: str  # "michael", "lorna", "izzy"
    meal_type: str  # "breakfast", "lunch", "dinner"
    recipe_name: Optional[str] = None  # Recipe name or None/"—" for blank

class BulkMealUpdate(BaseModel):
    """Batch update from HA - all meal selections at once"""
    week_start: date
    meals: List[MealSelection]

class SnackSelection(BaseModel):
    """Single snack toggle from HA"""
    date: date
    person: str
    snack_name: str
    consumed: bool

class BulkSnackUpdate(BaseModel):
    """Batch update from HA - all snack selections"""
    snacks: List[SnackSelection]