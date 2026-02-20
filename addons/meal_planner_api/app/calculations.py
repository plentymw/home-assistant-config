"""
Core calculation logic for meal planning.
- Daily/weekly totals per person
- Shopping list generation with Wed/Sun batch cook split
- Cost and nutrition calculations
"""

from datetime import date, timedelta
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from collections import defaultdict

from database import WeekPlan, RecipePortion, Ingredient, SnackLog, Snack, Person, Recipe


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_week_start(target_date: date = None) -> date:
    """Get Monday of the week containing target_date"""
    if target_date is None:
        target_date = date.today()
    return target_date - timedelta(days=target_date.weekday())


def get_day_name(day_date: date) -> str:
    """Convert date to day name (mon, tue, wed, etc.)"""
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return days[day_date.weekday()]


def is_wed_batch(meal_date: date, meal_type: str) -> bool:
    """
    Determine if a meal belongs to Wednesday batch cook.
    
    Wed cook covers: Wed dinner through Sun lunch inclusive
    Sun cook covers: Sun dinner through Wed lunch inclusive
    """
    day_name = get_day_name(meal_date)
    
    # Wed dinner through Sun lunch
    if day_name == "wed" and meal_type == "dinner":
        return True
    if day_name in ["thu", "fri", "sat"]:
        return True
    if day_name == "sun" and meal_type in ["breakfast", "lunch"]:
        return True
    
    return False


# ============================================================================
# DAILY TOTALS
# ============================================================================

def calculate_daily_totals(db: Session, target_date: date) -> Dict[str, Dict[str, float]]:
    """
    Calculate nutrition totals for each person for a specific day.
    
    Returns: {
        "Michael": {"kcal": 2000, "protein": 150, "carbs": 200, "fat": 70},
        "Lorna": {...},
        "Izzy": {...}
    }
    """
    totals = defaultdict(lambda: {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0})
    
    # Get all people
    people = db.query(Person).all()
    person_map = {p.id: p.name for p in people}
    
    # 1. Add meals from week plan
    meals = db.query(WeekPlan).filter(WeekPlan.date == target_date).all()
    
    for meal in meals:
        if not meal.recipe_id:
            continue
        
        person_name = person_map.get(meal.person_id)
        if not person_name:
            continue
        
        # Get recipe portions for this person
        portions = db.query(RecipePortion).filter(
            RecipePortion.recipe_id == meal.recipe_id,
            RecipePortion.person_id == meal.person_id
        ).all()
        
        for portion in portions:
            ingredient = db.query(Ingredient).filter(Ingredient.id == portion.ingredient_id).first()
            if not ingredient:
                continue
            
            qty = portion.quantity
            totals[person_name]["kcal"] += ingredient.kcal_per_unit * qty
            totals[person_name]["protein"] += ingredient.protein_per_unit * qty
            totals[person_name]["carbs"] += ingredient.carbs_per_unit * qty
            totals[person_name]["fat"] += ingredient.fat_per_unit * qty
    
    # 2. Add snacks from snack log
    snacks = db.query(SnackLog).filter(
        SnackLog.date == target_date,
        SnackLog.consumed == True
    ).all()
    
    for snack_entry in snacks:
        person_name = person_map.get(snack_entry.person_id)
        if not person_name:
            continue
        
        snack = db.query(Snack).filter(Snack.id == snack_entry.snack_id).first()
        if not snack:
            continue
        
        ingredient = db.query(Ingredient).filter(Ingredient.id == snack.ingredient_id).first()
        if not ingredient:
            continue
        
        qty = snack.default_quantity
        totals[person_name]["kcal"] += ingredient.kcal_per_unit * qty
        totals[person_name]["protein"] += ingredient.protein_per_unit * qty
        totals[person_name]["carbs"] += ingredient.carbs_per_unit * qty
        totals[person_name]["fat"] += ingredient.fat_per_unit * qty
    
    return dict(totals)


# ============================================================================
# WEEKLY TOTALS
# ============================================================================

def calculate_weekly_totals(db: Session, week_start: date) -> Dict[str, Dict[str, float]]:
    """
    Calculate nutrition totals for each person for entire week.
    
    Returns: {
        "Michael": {"kcal": 14000, "protein": 1050, "carbs": 1400, "fat": 490},
        "Lorna": {...},
        "Izzy": {...}
    }
    """
    totals = defaultdict(lambda: {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0})
    
    # Sum up each day of the week
    for day_offset in range(7):
        day_date = week_start + timedelta(days=day_offset)
        day_totals = calculate_daily_totals(db, day_date)
        
        for person, nutrients in day_totals.items():
            totals[person]["kcal"] += nutrients["kcal"]
            totals[person]["protein"] += nutrients["protein"]
            totals[person]["carbs"] += nutrients["carbs"]
            totals[person]["fat"] += nutrients["fat"]
    
    return dict(totals)


# ============================================================================
# COST CALCULATION
# ============================================================================

def calculate_daily_cost(db: Session, target_date: date) -> float:
    """Calculate total cost for all meals on a specific day"""
    total_cost = 0.0
    
    # 1. Meals
    meals = db.query(WeekPlan).filter(WeekPlan.date == target_date).all()
    
    for meal in meals:
        if not meal.recipe_id:
            continue
        
        portions = db.query(RecipePortion).filter(
            RecipePortion.recipe_id == meal.recipe_id,
            RecipePortion.person_id == meal.person_id
        ).all()
        
        for portion in portions:
            ingredient = db.query(Ingredient).filter(Ingredient.id == portion.ingredient_id).first()
            if ingredient:
                total_cost += ingredient.cost_per_unit * portion.quantity
    
    # 2. Snacks
    snacks = db.query(SnackLog).filter(
        SnackLog.date == target_date,
        SnackLog.consumed == True
    ).all()
    
    for snack_entry in snacks:
        snack = db.query(Snack).filter(Snack.id == snack_entry.snack_id).first()
        if not snack:
            continue
        
        ingredient = db.query(Ingredient).filter(Ingredient.id == snack.ingredient_id).first()
        if ingredient:
            total_cost += ingredient.cost_per_unit * snack.default_quantity
    
    return round(total_cost, 2)


def calculate_weekly_cost(db: Session, week_start: date) -> float:
    """Calculate total cost for entire week"""
    total_cost = 0.0
    
    for day_offset in range(7):
        day_date = week_start + timedelta(days=day_offset)
        total_cost += calculate_daily_cost(db, day_date)
    
    return round(total_cost, 2)


# ============================================================================
# SHOPPING LIST GENERATION
# ============================================================================

def generate_shopping_list(db: Session, week_start: date, batch: str) -> List[Dict]:
    """
    Generate shopping list for either Wed or Sun batch cook.
    
    batch: "wed" or "sun"
    
    Returns: [
        {"ingredient": "Chicken", "quantity": 1.5, "unit": "kg", "cost": 9.19},
        ...
    ]
    """
    # Consolidate ingredients
    ingredient_totals = defaultdict(float)
    
    # Iterate through the week
    for day_offset in range(7):
        day_date = week_start + timedelta(days=day_offset)
        
        # Get meals for this day
        meals = db.query(WeekPlan).filter(WeekPlan.date == day_date).all()
        
        for meal in meals:
            if not meal.recipe_id:
                continue
            
            # Check if this meal belongs to the requested batch
            if batch == "wed":
                if not is_wed_batch(day_date, meal.meal_type):
                    continue
            else:  # sun batch
                if is_wed_batch(day_date, meal.meal_type):
                    continue
            
            # Get portions for this meal
            portions = db.query(RecipePortion).filter(
                RecipePortion.recipe_id == meal.recipe_id,
                RecipePortion.person_id == meal.person_id
            ).all()
            
            for portion in portions:
                ingredient_totals[portion.ingredient_id] += portion.quantity
    
    # Convert to shopping list with ingredient details
    shopping_list = []
    
    for ingredient_id, total_qty in ingredient_totals.items():
        ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
        if not ingredient:
            continue
        
        # Calculate cost
        cost = ingredient.cost_per_unit * total_qty
        
        # Convert grams to kg if applicable
        display_qty = total_qty
        display_unit = ingredient.unit
        
        if ingredient.unit == "g" and total_qty >= 1000:
            display_qty = total_qty / 1000
            display_unit = "kg"
        
        shopping_list.append({
            "ingredient": ingredient.name,
            "quantity": round(display_qty, 2),
            "unit": display_unit,
            "cost": round(cost, 2)
        })
    
    # Sort by ingredient name
    shopping_list.sort(key=lambda x: x["ingredient"])
    
    return shopping_list


# ============================================================================
# COMPLETE WEEK SUMMARY
# ============================================================================

def calculate_week_summary(db: Session, week_start: date = None) -> Dict:
    """
    Calculate complete summary for HA to read.
    Includes today totals, week totals, shopping lists, costs.
    """
    if week_start is None:
        week_start = get_week_start()
    
    today = date.today()
    
    # Daily totals for today
    today_totals_raw = calculate_daily_totals(db, today)
    today_totals = [
        {
            "person": person,
            "kcal": round(vals["kcal"], 0),
            "protein": round(vals["protein"], 1),
            "carbs": round(vals["carbs"], 1),
            "fat": round(vals["fat"], 1)
        }
        for person, vals in today_totals_raw.items()
    ]
    
    # Weekly totals
    week_totals_raw = calculate_weekly_totals(db, week_start)
    week_totals = [
        {
            "person": person,
            "kcal": round(vals["kcal"], 0),
            "protein": round(vals["protein"], 1),
            "carbs": round(vals["carbs"], 1),
            "fat": round(vals["fat"], 1)
        }
        for person, vals in week_totals_raw.items()
    ]
    
    # Costs
    today_cost = calculate_daily_cost(db, today)
    week_cost = calculate_weekly_cost(db, week_start)
    
    # Shopping lists
    wed_shopping = generate_shopping_list(db, week_start, "wed")
    sun_shopping = generate_shopping_list(db, week_start, "sun")
    
    return {
        "today_cost": today_cost,
        "today_totals": today_totals,
        "week_cost": week_cost,
        "week_totals": week_totals,
        "wed_shopping": wed_shopping,
        "sun_shopping": sun_shopping,
        "week_start": week_start.isoformat(),
        "last_updated": date.today().isoformat()
    }