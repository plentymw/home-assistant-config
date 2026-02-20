"""
Database setup and connection for the meal planner.
Uses SQLite for simplicity - just a single file database.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Date, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

# SQLite database file location
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "mealplanner.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create engine
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# ============================================================================
# DATABASE MODELS (Tables)
# ============================================================================

class Person(Base):
    """People in the household (Michael, Lorna, Izzy)"""
    __tablename__ = "people"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # "Michael", "Lorna", "Izzy"


class Ingredient(Base):
    """Individual ingredients with nutrition and cost data"""
    __tablename__ = "ingredients"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    unit = Column(String, nullable=False)  # "g", "ml", "item"
    
    # Cost per unit (e.g., £0.006 per gram)
    cost_per_unit = Column(Float, default=0.0)
    
    # Nutrition per unit (e.g., per gram or per item)
    kcal_per_unit = Column(Float, default=0.0)
    protein_per_unit = Column(Float, default=0.0)
    carbs_per_unit = Column(Float, default=0.0)
    fat_per_unit = Column(Float, default=0.0)
    
    # Pack size info (for shopping list rounding)
    pack_size = Column(Float, nullable=True)  # e.g., 500 (grams in a pack)
    pack_cost = Column(Float, nullable=True)  # e.g., £3.00


class Recipe(Base):
    """Recipes/meals (Japanese Chicken, Steak, etc.)"""
    __tablename__ = "recipes"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    meal_type = Column(String, nullable=False)  # "breakfast", "lunch", "dinner", "snack"
    
    # Relationships
    portions = relationship("RecipePortion", back_populates="recipe", cascade="all, delete-orphan")


class RecipePortion(Base):
    """Per-person ingredient quantities for each recipe"""
    __tablename__ = "recipe_portions"
    
    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=False)
    
    # Quantity for this person (in ingredient's unit)
    quantity = Column(Float, nullable=False)
    
    # Relationships
    recipe = relationship("Recipe", back_populates="portions")
    ingredient = relationship("Ingredient")
    person = relationship("Person")


class WeekPlan(Base):
    """Weekly meal plan - which meals are scheduled when"""
    __tablename__ = "week_plan"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=False)
    meal_type = Column(String, nullable=False)  # "breakfast", "lunch", "dinner"
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=True)
    
    # Relationships
    person = relationship("Person")
    recipe = relationship("Recipe")


class Snack(Base):
    """Snack items (Apple, Banana, Vitamins, etc.)"""
    __tablename__ = "snacks"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    default_quantity = Column(Float, nullable=False)  # Default serving size
    
    # Relationship
    ingredient = relationship("Ingredient")


class SnackLog(Base):
    """Daily snack consumption tracking"""
    __tablename__ = "snack_log"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=False)
    snack_id = Column(Integer, ForeignKey("snacks.id"), nullable=False)
    consumed = Column(Boolean, default=False)
    
    # Relationships
    person = relationship("Person")
    snack = relationship("Snack")


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)
    print(f"✅ Database initialized at: {DB_PATH}")


def get_db():
    """
    Dependency for FastAPI routes.
    Creates a database session, yields it, then closes it.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# SEED DATA (Optional - run once to populate initial data)
# ============================================================================

def seed_initial_data():
    """Add basic people to get started"""
    db = SessionLocal()
    
    try:
        # Add people if they don't exist
        if db.query(Person).count() == 0:
            people = [
                Person(name="Michael"),
                Person(name="Lorna"),
                Person(name="Izzy")
            ]
            db.add_all(people)
            db.commit()
            print("✅ Added people: Michael, Lorna, Izzy")
        
        print("✅ Database seeded")
        
    except Exception as e:
        print(f"❌ Error seeding data: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    # Run this file directly to initialize database
    init_db()
    seed_initial_data()