#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Non-electrical carbon footprint activities API.

Allows adding carbon emissions from non-computer sources (driving, flights,
food, heating, etc.) so that an LLM or any external system can submit
activity data and get a unified carbon footprint report.

Usage:
    from carbon_tracker.activities import ActivityTracker, Activity

    tracker = ActivityTracker()
    tracker.add(Activity.driving(km=25, vehicle="petrol_car"))
    tracker.add(Activity.flight(km=800, flight_class="economy"))
    tracker.add(Activity.custom("Heating", co2_grams=1500, description="Gas heating 1 month"))
    print(tracker.report())
"""

import time
import json

from typing import Dict, List
from dataclasses import dataclass, field

from carbon_tracker.globals import (
    _VEHICLE_FACTORS,
    _FLIGHT_FACTORS,
    _FOOD_FACTORS,
    _ENERGY_FACTORS,
)


def get_vehicle_types() -> List[str]:
    """Return all supported vehicle type keys."""
    return list(_VEHICLE_FACTORS.keys())


def get_flight_classes() -> List[str]:
    """Return all supported flight class keys."""
    return list(_FLIGHT_FACTORS.keys())


def get_food_types() -> List[str]:
    """Return all supported food type keys."""
    return list(_FOOD_FACTORS.keys())


def get_energy_types() -> List[str]:
    """Return all supported energy/heating fuel type keys."""
    return list(_ENERGY_FACTORS.keys())


# ============================================================
# Activity data model
# ============================================================


@dataclass
class Activity:
    """
    A single carbon-emitting activity.

    Use the factory methods (driving, flight, food, heating, custom) to create
    activities with auto-calculated CO2 values.
    """

    category: str = ""  # e.g. "transport", "food", "energy", "other"
    name: str = ""  # e.g. "Driving to work"
    description: str = ""
    co2_grams: float = 0.0
    quantity: float = 0.0  # amount in the relevant unit
    unit: str = ""  # e.g. "km", "kg", "kWh", "item"
    factor_used: float = 0.0  # gCO2 per unit used in calculation
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, str] = field(default_factory=dict)

    # Factory methods
    @classmethod
    def driving(
        cls,
        km: float,
        vehicle: str = "petrol_car",
        description: str = "",
    ) -> "Activity":
        """Create a driving activity.

        Args:
            km: Distance driven in kilometers.
            vehicle: Vehicle type key (see get_vehicle_types()).
            description: Optional description.
        """
        factor = _VEHICLE_FACTORS.get(vehicle, _VEHICLE_FACTORS["petrol_car"])
        return cls(
            category="transport",
            name=f"Driving ({vehicle})",
            description=description or f"{km:.1f} km by {vehicle}",
            co2_grams=km * factor,
            quantity=km,
            unit="km",
            factor_used=factor,
            metadata={"vehicle": vehicle},
        )

    @classmethod
    def flight(
        cls,
        km: float,
        flight_class: str = "economy",
        description: str = "",
    ) -> "Activity":
        """Create a flight activity.

        Args:
            km: Flight distance in kilometers.
            flight_class: Class key (see get_flight_classes()).
            description: Optional description.
        """
        factor = _FLIGHT_FACTORS.get(flight_class, _FLIGHT_FACTORS["economy"])
        return cls(
            category="transport",
            name=f"Flight ({flight_class})",
            description=description or f"{km:.0f} km flight, {flight_class}",
            co2_grams=km * factor,
            quantity=km,
            unit="km",
            factor_used=factor,
            metadata={"flight_class": flight_class},
        )

    @classmethod
    def food(
        cls,
        food_type: str,
        kg: float,
        description: str = "",
    ) -> "Activity":
        """Create a food consumption activity.

        Args:
            food_type: Food type key (see get_food_types()).
            kg: Weight in kilograms.
            description: Optional description.
        """
        factor = _FOOD_FACTORS.get(food_type, 500.0)
        return cls(
            category="food",
            name=f"Food ({food_type})",
            description=description or f"{kg:.2f} kg of {food_type}",
            co2_grams=kg * factor,
            quantity=kg,
            unit="kg",
            factor_used=factor,
            metadata={"food_type": food_type},
        )

    @classmethod
    def heating(
        cls,
        kwh: float,
        fuel: str = "natural_gas",
        description: str = "",
    ) -> "Activity":
        """Create a heating/energy activity.

        Args:
            kwh: Energy consumed in kWh.
            fuel: Fuel type key (see get_energy_types()).
            description: Optional description.
        """
        factor = _ENERGY_FACTORS.get(fuel, _ENERGY_FACTORS["natural_gas"])
        return cls(
            category="energy",
            name=f"Heating ({fuel})",
            description=description or f"{kwh:.1f} kWh of {fuel}",
            co2_grams=kwh * factor,
            quantity=kwh,
            unit="kWh",
            factor_used=factor,
            metadata={"fuel": fuel},
        )

    @classmethod
    def custom(
        cls,
        name: str,
        co2_grams: float,
        description: str = "",
        category: str = "other",
        quantity: float = 1.0,
        unit: str = "item",
    ) -> "Activity":
        """Create a custom activity with a known CO2 value.

        Args:
            name: Activity name.
            co2_grams: Total CO2 in grams.
            description: Optional description.
            category: Category label.
            quantity: Amount.
            unit: Unit label.
        """
        return cls(
            category=category,
            name=name,
            description=description,
            co2_grams=co2_grams,
            quantity=quantity,
            unit=unit,
            factor_used=co2_grams / quantity if quantity > 0 else 0.0,
        )

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "name": self.name,
            "description": self.description,
            "co2_grams": self.co2_grams,
            "quantity": self.quantity,
            "unit": self.unit,
            "factor_used": self.factor_used,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Activity":
        obj = cls()
        obj.category = d.get("category", "other")
        obj.name = d.get("name", "")
        obj.description = d.get("description", "")
        obj.co2_grams = d.get("co2_grams", 0.0)
        obj.quantity = d.get("quantity", 0.0)
        obj.unit = d.get("unit", "")
        obj.factor_used = d.get("factor_used", 0.0)
        obj.timestamp = d.get("timestamp", 0.0)
        obj.metadata = d.get("metadata", {})
        return obj


# ============================================================
# Activity Tracker
# ============================================================


class ActivityTracker:
    """
    Collects non-electrical carbon footprint activities and produces reports.

    Designed to be called by an LLM (e.g., GPT) or any external API to
    aggregate carbon data from diverse sources alongside computer usage data.

    Usage:
        tracker = ActivityTracker()
        tracker.add(Activity.driving(km=30))
        tracker.add(Activity.food("beef", kg=0.3))
        tracker.add(Activity.custom("Cement work", co2_grams=5000))

        print(tracker.total_co2_grams())
        print(tracker.report())
        tracker.save("my_activities.json")
    """

    def __init__(self):
        self.activities: List[Activity] = []

    def add(self, activity: Activity):
        """Add an activity to the tracker."""
        self.activities.append(activity)

    def add_driving(
        self, km: float, vehicle: str = "petrol_car", description: str = ""
    ):
        """Shortcut: add a driving activity."""
        self.activities.append(Activity.driving(km, vehicle, description))

    def add_flight(
        self, km: float, flight_class: str = "economy", description: str = ""
    ):
        """Shortcut: add a flight activity."""
        self.activities.append(Activity.flight(km, flight_class, description))

    def add_food(self, food_type: str, kg: float, description: str = ""):
        """Shortcut: add a food consumption activity."""
        self.activities.append(Activity.food(food_type, kg, description))

    def add_heating(self, kwh: float, fuel: str = "natural_gas", description: str = ""):
        """Shortcut: add a heating/energy activity."""
        self.activities.append(Activity.heating(kwh, fuel, description))

    def add_custom(
        self,
        name: str,
        co2_grams: float,
        description: str = "",
        category: str = "other",
    ):
        """Shortcut: add a custom activity with known CO2 value."""
        self.activities.append(Activity.custom(name, co2_grams, description, category))

    def remove(self, index: int):
        """Remove an activity by index."""
        if 0 <= index < len(self.activities):
            self.activities.pop(index)

    def clear(self):
        """Remove all activities."""
        self.activities.clear()

    # ---- Aggregation ----

    def total_co2_grams(self) -> float:
        """Total CO2 across all activities in grams."""
        return sum(a.co2_grams for a in self.activities)

    def total_co2_kg(self) -> float:
        """Total CO2 across all activities in kilograms."""
        return self.total_co2_grams() / 1000.0

    def by_category(self) -> Dict[str, float]:
        """CO2 totals grouped by category (grams)."""
        cats: Dict[str, float] = {}
        for a in self.activities:
            cats[a.category] = cats.get(a.category, 0.0) + a.co2_grams
        return cats

    def equivalences(self) -> dict:
        """Convert total CO2 to real-world equivalences."""
        total = self.total_co2_grams()
        return {
            "driving_km": total / 120.0,
            "flight_km_economy": total / 133.0,
            "smartphone_charges": total / 8.3,
            "tree_days_to_offset": total / 60.0,
            "beef_kg_equivalent": total / 27000.0,
        }

    # ---- Reporting ----

    def report(self) -> str:
        """Generate a human-readable carbon footprint report."""
        lines = []
        lines.append("=" * 60)
        lines.append("  CARBON FOOTPRINT — ACTIVITIES REPORT")
        lines.append("=" * 60)
        lines.append("")

        if not self.activities:
            lines.append("  No activities recorded.")
            return "\n".join(lines)

        # Per-activity table
        lines.append(f"  {'#':<4} {'Category':<12} {'Name':<28} {'CO2 (g)':>10}")
        lines.append("  " + "-" * 56)
        for i, a in enumerate(self.activities, 1):
            lines.append(f"  {i:<4} {a.category:<12} {a.name:<28} {a.co2_grams:>10.1f}")
        lines.append("  " + "-" * 56)
        lines.append(f"  {'':4} {'':12} {'TOTAL':<28} {self.total_co2_grams():>10.1f}")
        lines.append("")

        # By category
        cats = self.by_category()
        lines.append("  === BY CATEGORY ===")
        total = self.total_co2_grams()
        for cat, co2 in sorted(cats.items(), key=lambda x: -x[1]):
            pct = (co2 / total * 100) if total > 0 else 0
            bar = "#" * int(pct / 4)
            lines.append(f"    {cat:<16} {co2:>10.1f} g  ({pct:>5.1f}%)  {bar}")
        lines.append("")

        # Summary
        lines.append("  === SUMMARY ===")
        lines.append(f"    Total CO2:       {total:.1f} g ({total / 1000:.3f} kg)")

        eq = self.equivalences()
        lines.append(f"    Driving equiv:   {eq['driving_km']:.2f} km by car")
        lines.append(
            f"    Flight equiv:    {eq['flight_km_economy']:.1f} km economy flight"
        )
        lines.append(f"    Tree offset:     {eq['tree_days_to_offset']:.2f} tree-days")
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ---- Persistence ----

    def save(self, filepath: str):
        """Save activities to a JSON file."""
        data = {
            "version": "1.1",
            "type": "carbon_activities",
            "timestamp": time.time(),
            "total_co2_grams": self.total_co2_grams(),
            "activities": [a.to_dict() for a in self.activities],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "ActivityTracker":
        """Load activities from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        tracker = cls()
        tracker.activities = [Activity.from_dict(a) for a in data.get("activities", [])]
        return tracker

    def to_dict_list(self) -> List[dict]:
        """Export all activities as list of dicts (for LLM/API integration)."""
        return [a.to_dict() for a in self.activities]

    @classmethod
    def from_dict_list(cls, items: List[dict]) -> "ActivityTracker":
        """Create tracker from a list of activity dicts (from LLM/API)."""
        tracker = cls()
        tracker.activities = [Activity.from_dict(d) for d in items]
        return tracker
