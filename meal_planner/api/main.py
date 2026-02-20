"""
FastAPI application for the meal planner.
This is the HTTP server that Home Assistant communicates with.
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from datetime import date, timedelta

import database
import models
import calculations

# Initialize database
database.init_db()

# Create FastAPI app
app = FastAPI(
    title="Meal Planner API",
    description="Backend for Home Assistant meal planning system",
    version="1.0.0"
)

# Enable CORS (so HA can access from different origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# MAIN ENDPOINT (What HA Reads)
# ============================================================================

@app.get("/week-totals", response_model=models.WeekTotalsResponse)
def get_week_totals(db: Session = Depends(database.get_db)):
    """
    Main endpoint for Home Assistant to read.
    Returns complete weekly summary with all totals and shopping lists.
    """
    week_start = calculations.get_week_start()
    summary = calculations.calculate_week_summary(db, week_start)
    return summary


@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Meal Planner API",
        "version": "1.0.0"
    }


# ============================================================================
# PEOPLE ENDPOINTS
# ============================================================================

@app.get("/people", response_model=List[models.Person])
def list_people(db: Session = Depends(database.get_db)):
    """List all people in the household"""
    return db.query(database.Person).all()


@app.post("/people", response_model=models.Person)
def create_person(person: models.PersonCreate, db: Session = Depends(database.get_db)):
    """Add a new person"""
    db_person = database.Person(name=person.name)
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


# ============================================================================
# INGREDIENT ENDPOINTS
# ============================================================================

@app.get("/ingredients", response_model=List[models.Ingredient])
def list_ingredients(db: Session = Depends(database.get_db)):
    """List all ingredients"""
    return db.query(database.Ingredient).all()


@app.get("/ingredients/{ingredient_id}", response_model=models.Ingredient)
def get_ingredient(ingredient_id: int, db: Session = Depends(database.get_db)):
    """Get specific ingredient details"""
    ingredient = db.query(database.Ingredient).filter(database.Ingredient.id == ingredient_id).first()
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return ingredient


@app.post("/ingredients", response_model=models.Ingredient)
def create_ingredient(ingredient: models.IngredientCreate, db: Session = Depends(database.get_db)):
    """Create new ingredient"""
    db_ingredient = database.Ingredient(**ingredient.dict())
    db.add(db_ingredient)
    db.commit()
    db.refresh(db_ingredient)
    return db_ingredient


@app.put("/ingredients/{ingredient_id}", response_model=models.Ingredient)
def update_ingredient(
    ingredient_id: int,
    ingredient: models.IngredientUpdate,
    db: Session = Depends(database.get_db)
):
    """Update ingredient details"""
    db_ingredient = db.query(database.Ingredient).filter(database.Ingredient.id == ingredient_id).first()
    if not db_ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    
    # Update only provided fields
    for key, value in ingredient.dict(exclude_unset=True).items():
        setattr(db_ingredient, key, value)
    
    db.commit()
    db.refresh(db_ingredient)
    return db_ingredient


@app.delete("/ingredients/{ingredient_id}")
def delete_ingredient(ingredient_id: int, db: Session = Depends(database.get_db)):
    """Delete ingredient"""
    db_ingredient = db.query(database.Ingredient).filter(database.Ingredient.id == ingredient_id).first()
    if not db_ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    
    db.delete(db_ingredient)
    db.commit()
    return {"message": "Ingredient deleted"}


# ============================================================================
# RECIPE ENDPOINTS
# ============================================================================

@app.get("/recipes", response_model=List[models.Recipe])
def list_recipes(meal_type: str = None, db: Session = Depends(database.get_db)):
    """List all recipes, optionally filtered by meal type"""
    query = db.query(database.Recipe)
    if meal_type:
        query = query.filter(database.Recipe.meal_type == meal_type)
    return query.all()


@app.get("/recipes/{recipe_id}", response_model=models.Recipe)
def get_recipe(recipe_id: int, db: Session = Depends(database.get_db)):
    """Get recipe with all portions"""
    recipe = db.query(database.Recipe).filter(database.Recipe.id == recipe_id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@app.post("/recipes", response_model=models.Recipe)
def create_recipe(recipe: models.RecipeCreate, db: Session = Depends(database.get_db)):
    """Create new recipe with portions"""
    db_recipe = database.Recipe(name=recipe.name, meal_type=recipe.meal_type)
    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    
    # Add portions
    for portion in recipe.portions:
        db_portion = database.RecipePortion(
            recipe_id=db_recipe.id,
            ingredient_id=portion.ingredient_id,
            person_id=portion.person_id,
            quantity=portion.quantity
        )
        db.add(db_portion)
    
    db.commit()
    db.refresh(db_recipe)
    return db_recipe


@app.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: int, db: Session = Depends(database.get_db)):
    """Delete recipe and all its portions"""
    db_recipe = db.query(database.Recipe).filter(database.Recipe.id == recipe_id).first()
    if not db_recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    db.delete(db_recipe)
    db.commit()
    return {"message": "Recipe deleted"}


# ============================================================================
# WEEK PLAN ENDPOINTS (HA Writes Here)
# ============================================================================

@app.get("/week-plan", response_model=List[models.WeekPlan])
def get_week_plan(week_start: date = None, db: Session = Depends(database.get_db)):
    """Get current week's meal plan"""
    if week_start is None:
        week_start = calculations.get_week_start()
    
    week_end = week_start + timedelta(days=6)
    
    plans = db.query(database.WeekPlan).filter(
        database.WeekPlan.date >= week_start,
        database.WeekPlan.date <= week_end
    ).all()
    
    return plans


@app.post("/week-plan/bulk-update")
def bulk_update_week_plan(update: models.BulkMealUpdate, db: Session = Depends(database.get_db)):
    """
    Bulk update meal plan from Home Assistant.
    HA sends all selections at once.
    """
    # Map person names to IDs
    people = db.query(database.Person).all()
    person_map = {p.name.lower(): p.id for p in people}
    
    # Map recipe names to IDs
    recipes = db.query(database.Recipe).all()
    recipe_map = {r.name.lower(): r.id for r in recipes}
    
    # Day name to offset
    day_offsets = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    
    updated_count = 0
    
    for meal in update.meals:
        # Calculate date
        day_offset = day_offsets.get(meal.day.lower())
        if day_offset is None:
            continue
        
        meal_date = update.week_start + timedelta(days=day_offset)
        
        # Get person ID
        person_id = person_map.get(meal.person.lower())
        if not person_id:
            continue
        
        # Get recipe ID (None if blank/"—")
        recipe_id = None
        if meal.recipe_name and meal.recipe_name != "—":
            recipe_id = recipe_map.get(meal.recipe_name.lower())
        
        # Find or create week plan entry
        plan = db.query(database.WeekPlan).filter(
            database.WeekPlan.date == meal_date,
            database.WeekPlan.person_id == person_id,
            database.WeekPlan.meal_type == meal.meal_type.lower()
        ).first()
        
        if plan:
            # Update existing
            plan.recipe_id = recipe_id
        else:
            # Create new
            plan = database.WeekPlan(
                date=meal_date,
                person_id=person_id,
                meal_type=meal.meal_type.lower(),
                recipe_id=recipe_id
            )
            db.add(plan)
        
        updated_count += 1
    
    db.commit()
    
    return {"message": f"Updated {updated_count} meal selections"}


# ============================================================================
# SNACK ENDPOINTS
# ============================================================================

@app.get("/snacks", response_model=List[models.Snack])
def list_snacks(db: Session = Depends(database.get_db)):
    """List all available snacks"""
    return db.query(database.Snack).all()


@app.post("/snacks", response_model=models.Snack)
def create_snack(snack: models.SnackCreate, db: Session = Depends(database.get_db)):
    """Create new snack item"""
    db_snack = database.Snack(**snack.dict())
    db.add(db_snack)
    db.commit()
    db.refresh(db_snack)
    return db_snack


@app.post("/snack-log/bulk-update")
def bulk_update_snack_log(update: models.BulkSnackUpdate, db: Session = Depends(database.get_db)):
    """
    Bulk update snack log from Home Assistant.
    HA sends all toggle states at once.
    """
    # Map names to IDs
    people = db.query(database.Person).all()
    person_map = {p.name.lower(): p.id for p in people}
    
    snacks = db.query(database.Snack).all()
    snack_map = {s.name.lower(): s.id for s in snacks}
    
    updated_count = 0
    
    for snack_sel in update.snacks:
        person_id = person_map.get(snack_sel.person.lower())
        snack_id = snack_map.get(snack_sel.snack_name.lower())
        
        if not person_id or not snack_id:
            continue
        
        # Find or create snack log entry
        log = db.query(database.SnackLog).filter(
            database.SnackLog.date == snack_sel.date,
            database.SnackLog.person_id == person_id,
            database.SnackLog.snack_id == snack_id
        ).first()
        
        if log:
            log.consumed = snack_sel.consumed
        else:
            log = database.SnackLog(
                date=snack_sel.date,
                person_id=person_id,
                snack_id=snack_id,
                consumed=snack_sel.consumed
            )
            db.add(log)
        
        updated_count += 1
    
    db.commit()
    
    return {"message": f"Updated {updated_count} snack log entries"}


# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
def startup_event():
    """Run when API starts"""
    print("=" * 60)
    print("🍽️  Meal Planner API Starting")
    print("=" * 60)
    database.seed_initial_data()
    print("✅ API ready at http://localhost:8000")
    print("📖 Docs available at http://localhost:8000/docs")
    print("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)