import requests
import datetime

class NotionMealSync(hass.Hass):
    def initialize(self):
        self.notion_token = self.args["notion_token"]
        self.database_id = self.args["database_id"]
        self.poll_mins = int(self.args.get("poll_mins", 5))
        self.enable_ha_to_notion = bool(self.args.get("enable_ha_to_notion", True))

        # Notion schema we already agreed
        self.PROP_WEEKSTART = "WeekStart"
        self.PROP_DAY = "Day"
        self.PROP_MEALTYPE = "MealType"
        self.PROP_PERSON = "Person"
        self.PROP_MEAL = "Meal"
        self.PROP_PREP = "PrepNotes"
        self.PROP_COOK = "CookNotes"
        self.PROP_WEDSHOP = "WedShop"
        self.PROP_SUNSHOP = "SunShop"

        self.DAY_LABEL_TO_SUFFIX = {"Mon": "mon", "Tue": "tue", "Wed": "wed", "Thu": "thu", "Fri": "fri", "Sat": "sat", "Sun": "sun"}
        self.SUFFIX_TO_DAY_LABEL = {v: k for k, v in self.DAY_LABEL_TO_SUFFIX.items()}

        self.PERSON_LABEL_TO_SUFFIX = {"Michael": "michael", "Lorna": "lorna", "Izzy": "izzy"}
        self.SUFFIX_TO_PERSON_LABEL = {v: k for k, v in self.PERSON_LABEL_TO_SUFFIX.items()}

        self.MEALTYPE_LABEL_TO_PREFIX = {"Dinner": "meal_dinner", "Lunch": "meal_lunch", "Breakfast": "meal_breakfast"}
        self.PREFIX_TO_MEALTYPE_LABEL = {"meal_dinner": "Dinner", "meal_lunch": "Lunch", "meal_breakfast": "Breakfast"}

        # Poll Notion -> HA
        self.run_every(self.sync_notion_to_ha, self.datetime() + datetime.timedelta(seconds=5), self.poll_mins * 60)

        # Listen HA -> Notion
        if self.enable_ha_to_notion:
            for ent in self.entities_to_watch():
                self.listen_state(self.on_ha_change, ent)

        self.log("NotionMealSync initialised (schema: WeekStart/Day/MealType/Person/Meal/PrepNotes/CookNotes/WedShop/SunShop)")

    # -------------------------
    # HA entity set
    # -------------------------
    def entities_to_watch(self):
        ents = []

        # Notes
        for d in self.DAY_LABEL_TO_SUFFIX.values():
            ents.append(f"input_text.prep_notes_{d}")
            ents.append(f"input_text.cook_notes_{d}")

        # Shopping lists
        ents.append("input_text.wed_food_shop_list")
        ents.append("input_text.sun_food_shop_list")

        # Meals per person per day
        for day in self.DAY_LABEL_TO_SUFFIX.values():
            for person in self.PERSON_LABEL_TO_SUFFIX.values():
                ents.append(f"input_select.meal_dinner_{day}_{person}")
                ents.append(f"input_select.meal_lunch_{day}_{person}")
                ents.append(f"input_select.meal_breakfast_{day}_{person}")

        return ents

    def set_helper(self, entity_id, value):
        domain = entity_id.split(".")[0]
        if domain == "input_text":
            self.call_service("input_text/set_value", entity_id=entity_id, value=value or "")
            return

        if domain == "input_select":
            option = value if value else "—"
            self.call_service("input_select/select_option", entity_id=entity_id, option=option)
            return

        self.log(f"Unsupported helper domain: {entity_id}", level="WARNING")

    # -------------------------
    # Notion API helpers
    # -------------------------
    def notion_headers(self):
        return {
            "Authorization": f"Bearer {self.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def monday_of_this_week(self):
        today = datetime.date.today()
        return today - datetime.timedelta(days=today.weekday())

    def notion_query_week(self, week_start_date):
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload = {
            "page_size": 100,
            "filter": {
                "property": self.PROP_WEEKSTART,
                "date": {"equals": week_start_date.isoformat()}
            }
        }
        r = requests.post(url, headers=self.notion_headers(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])

    def get_select(self, props, name):
        p = props.get(name)
        if not p:
            return None
        sel = p.get("select")
        return sel.get("name") if sel else None

    def get_text(self, props, name):
        p = props.get(name)
        if not p:
            return ""
        rt = p.get("rich_text") or []
        return "".join([x.get("plain_text", "") for x in rt]).strip()

    def set_select(self, page_id, prop_name, value):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"properties": {prop_name: {"select": {"name": value}}}}
        r = requests.patch(url, headers=self.notion_headers(), json=payload, timeout=30)
        r.raise_for_status()

    def set_text(self, page_id, prop_name, value):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"properties": {prop_name: {"rich_text": [{"type": "text", "text": {"content": value or ""}}]}}}
        r = requests.patch(url, headers=self.notion_headers(), json=payload, timeout=30)
        r.raise_for_status()

    # -------------------------
    # Notion -> HA
    # -------------------------
    def sync_notion_to_ha(self, kwargs):
        try:
            week_start = self.monday_of_this_week()
            rows = self.notion_query_week(week_start)

            # Index Notion rows by (Day, MealType, Person)
            idx = {}
            wed_shop = ""
            sun_shop = ""

            for page in rows:
                page_id = page["id"]
                props = page.get("properties", {})

                day = self.get_select(props, self.PROP_DAY)
                mealtype = self.get_select(props, self.PROP_MEALTYPE)
                person = self.get_select(props, self.PROP_PERSON)

                meal = self.get_select(props, self.PROP_MEAL) or ""
                prep = self.get_text(props, self.PROP_PREP)
                cook = self.get_text(props, self.PROP_COOK)

                if not wed_shop:
                    wed_shop = self.get_text(props, self.PROP_WEDSHOP)
                if not sun_shop:
                    sun_shop = self.get_text(props, self.PROP_SUNSHOP)

                if day and mealtype and person:
                    idx[(day, mealtype, person)] = {"page_id": page_id, "meal": meal, "prep": prep, "cook": cook}

            # Shopping lists
            self.set_helper("input_text.wed_food_shop_list", wed_shop)
            self.set_helper("input_text.sun_food_shop_list", sun_shop)

            # Day notes: take from the Michael Dinner row if present, else first row found for that day
            for day_label, day_suffix in self.DAY_LABEL_TO_SUFFIX.items():
                picked = idx.get((day_label, "Dinner", "Michael"))
                if not picked:
                    for mt in ("Dinner", "Lunch", "Breakfast"):
                        for p in ("Michael", "Lorna", "Izzy"):
                            if (day_label, mt, p) in idx:
                                picked = idx[(day_label, mt, p)]
                                break
                        if picked:
                            break
                if picked:
                    self.set_helper(f"input_text.prep_notes_{day_suffix}", picked.get("prep", ""))
                    self.set_helper(f"input_text.cook_notes_{day_suffix}", picked.get("cook", ""))

            # Meals
            for (day_label, mealtype_label, person_label), data in idx.items():
                if mealtype_label not in self.MEALTYPE_LABEL_TO_PREFIX:
                    continue
                if day_label not in self.DAY_LABEL_TO_SUFFIX:
                    continue
                if person_label not in self.PERSON_LABEL_TO_SUFFIX:
                    continue

                prefix = self.MEALTYPE_LABEL_TO_PREFIX[mealtype_label]
                day_suffix = self.DAY_LABEL_TO_SUFFIX[day_label]
                person_suffix = self.PERSON_LABEL_TO_SUFFIX[person_label]
                ent = f"input_select.{prefix}_{day_suffix}_{person_suffix}"

                self.set_helper(ent, data.get("meal") or "—")

            self.log("Notion -> HA sync complete")

        except Exception as e:
            self.log(f"Notion -> HA sync failed: {e}", level="ERROR")

    # -------------------------
    # HA -> Notion
    # -------------------------
    def on_ha_change(self, entity, attribute, old, new, kwargs):
        if old == new:
            return

        try:
            week_start = self.monday_of_this_week()
            rows = self.notion_query_week(week_start)

            # Build a minimal list of pages with their keys
            pages = []
            for page in rows:
                props = page.get("properties", {})
                pages.append({
                    "id": page["id"],
                    "day": self.get_select(props, self.PROP_DAY),
                    "mealtype": self.get_select(props, self.PROP_MEALTYPE),
                    "person": self.get_select(props, self.PROP_PERSON),
                })

            # Shopping lists -> write to all pages (keeps it simple)
            if entity == "input_text.wed_food_shop_list":
                for p in pages:
                    self.set_text(p["id"], self.PROP_WEDSHOP, new or "")
                return

            if entity == "input_text.sun_food_shop_list":
                for p in pages:
                    self.set_text(p["id"], self.PROP_SUNSHOP, new or "")
                return

            # Prep/Cook notes per day -> write to all pages for that day
            if entity.startswith("input_text.prep_notes_"):
                day_suffix = entity.split("_")[-1]
                day_label = self.SUFFIX_TO_DAY_LABEL.get(day_suffix)
                if day_label:
                    for p in pages:
                        if p["day"] == day_label:
                            self.set_text(p["id"], self.PROP_PREP, new or "")
                return

            if entity.startswith("input_text.cook_notes_"):
                day_suffix = entity.split("_")[-1]
                day_label = self.SUFFIX_TO_DAY_LABEL.get(day_suffix)
                if day_label:
                    for p in pages:
                        if p["day"] == day_label:
                            self.set_text(p["id"], self.PROP_COOK, new or "")
                return

            # Meals: input_select.meal_dinner_mon_michael
            if entity.startswith("input_select.meal_"):
                name = entity.split(".")[1]
                parts = name.split("_")
                # parts: meal, dinner|lunch|breakfast, mon..sun, michael|lorna|izzy
                prefix = "_".join(parts[0:2])  # meal_dinner etc
                day_suffix = parts[2]
                person_suffix = parts[3]

                mealtype_label = self.PREFIX_TO_MEALTYPE_LABEL.get(prefix)
                day_label = self.SUFFIX_TO_DAY_LABEL.get(day_suffix)
                person_label = self.SUFFIX_TO_PERSON_LABEL.get(person_suffix)

                if not (mealtype_label and day_label and person_label):
                    return

                # Find matching Notion page
                for p in pages:
                    if p["day"] == day_label and p["mealtype"] == mealtype_label and p["person"] == person_label:
                        self.set_select(p["id"], self.PROP_MEAL, new or "—")
                        return

        except Exception as e:
            self.log(f"HA -> Notion update failed for {entity}: {e}", level="WARNING")
