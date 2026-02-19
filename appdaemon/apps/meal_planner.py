import requests
from datetime import timedelta

import appdaemon.plugins.hass.hassapi as hass


class MealPlanner(hass.Hass):
    """
    Syncs:
      - Notion Plan DB -> HA input_select helpers (Dinner/Lunch/Breakfast)
      - HA helper changes -> Notion Plan DB upsert

    Assumptions based on your screenshots:
      Plan properties:
        - Title: Name
        - date (date)
        - person (select)
        - meal (relation -> Meals)

      Meals properties:
        - Title: Name
        - MealType (select): dinner / lunch / breakfast (and maybe smoothie etc)
    """

    def initialize(self):
        self.log("MealPlanner v1 starting")

        self.notion_token = self.args.get("notion_token")
        if not self.notion_token:
            self.error("Missing notion_token in apps.yaml")
            return

        self.db_plan = self.args.get("db_plan")
        self.db_meals = self.args.get("db_meals")
        self.sync_interval_seconds = int(self.args.get("sync_interval_seconds", 60))

        if not self.db_plan or not self.db_meals:
            self.error("Missing db_plan or db_meals in apps.yaml")
            return

        self.headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        # prevent loop: when we write to HA from Notion sync, don't write straight back to Notion
        self._ignore_ha_events_until = None

        # Listen for user changes in HA
        self._listen_to_meal_helpers()

        # Periodic pull from Notion
        self.run_every(self._sync_from_notion, self.datetime(), self.sync_interval_seconds)

        self.log("MealPlanner initialized")

    # ---------------------------
    # Notion helpers
    # ---------------------------

    def _notion_post(self, url, payload):
        r = requests.post(url, headers=self.headers, json=payload, timeout=25)
        if r.status_code >= 400:
            self.error(f"Notion POST {url} failed {r.status_code}: {r.text[:300]}")
            return None
        return r.json()

    def _notion_patch(self, url, payload):
        r = requests.patch(url, headers=self.headers, json=payload, timeout=25)
        if r.status_code >= 400:
            self.error(f"Notion PATCH {url} failed {r.status_code}: {r.text[:300]}")
            return None
        return r.json()

    def _notion_get(self, url):
        r = requests.get(url, headers=self.headers, timeout=25)
        if r.status_code >= 400:
            self.error(f"Notion GET {url} failed {r.status_code}: {r.text[:300]}")
            return None
        return r.json()

    def _query_database(self, db_id, payload):
        url = f"https://api.notion.com/v1/databases/{db_id}/query"
        return self._notion_post(url, payload)

    def _get_page(self, page_id):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        return self._notion_get(url)

    def _create_page(self, payload):
        url = "https://api.notion.com/v1/pages"
        return self._notion_post(url, payload)

    def _update_page(self, page_id, payload):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        return self._notion_patch(url, payload)

    # ---------------------------
    # Time / week mapping
    # ---------------------------

    def _week_start(self, dt):
        # Monday start (0 = Monday)
        return (dt - timedelta(days=dt.weekday())).date()

    def _date_for_dow(self, week_start_date, dow_short):
        # dow_short: mon,tue,wed,thu,fri,sat,sun
        order = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        idx = order.index(dow_short)
        return week_start_date + timedelta(days=idx)

    # ---------------------------
    # HA entity mapping
    # ---------------------------

    def _listen_to_meal_helpers(self):
        # Dinner
        for dow in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
            for person in ["michael", "lorna", "izzy"]:
                self.listen_state(
                    self._on_ha_meal_changed,
                    f"input_select.meal_dinner_{dow}_{person}",
                    meal_type="dinner",
                    dow=dow,
                    person=person,
                )
                self.listen_state(
                    self._on_ha_meal_changed,
                    f"input_select.meal_lunch_{dow}_{person}",
                    meal_type="lunch",
                    dow=dow,
                    person=person,
                )
                self.listen_state(
                    self._on_ha_meal_changed,
                    f"input_select.meal_breakfast_{dow}_{person}",
                    meal_type="breakfast",
                    dow=dow,
                    person=person,
                )

    def _set_ha_helper(self, meal_type, dow, person, meal_name):
        entity = f"input_select.meal_{meal_type}_{dow}_{person}"
        # Only write if different to avoid churn
        current = self.get_state(entity)
        if current != meal_name:
            self.select_option(entity, meal_name)

    # ---------------------------
    # Notion -> HA sync
    # ---------------------------

    def _sync_from_notion(self, kwargs):
        try:
            now = self.datetime()
            week_start = self._week_start(now)

            # Ignore HA state listeners while we write from Notion
            self._ignore_ha_events_until = self.datetime() + timedelta(seconds=5)

            # Pull all Plan entries from this week (Mon..Sun)
            start_iso = str(week_start)
            end_iso = str(week_start + timedelta(days=6))

            payload = {
                "filter": {
                    "and": [
                        {
                            "property": "date",
                            "date": {"on_or_after": start_iso},
                        },
                        {
                            "property": "date",
                            "date": {"on_or_before": end_iso},
                        },
                    ]
                },
                "page_size": 100,
            }

            res = self._query_database(self.db_plan, payload)
            if not res:
                return

            pages = res.get("results", [])

            # Cache meal page lookups (meal_page_id -> (meal_name, meal_type))
            meal_cache = {}

            for p in pages:
                props = p.get("properties", {})
                date_prop = props.get("date", {}).get("date", {})
                person_prop = props.get("person", {}).get("select", {})
                meal_rel = props.get("meal", {}).get("relation", [])

                if not date_prop or not person_prop or not meal_rel:
                    continue

                date_str = date_prop.get("start")
                if not date_str:
                    continue

                # date_str may include time, we only need YYYY-MM-DD
                date_only = date_str[:10]
                person = person_prop.get("name", "").strip()
                if not person:
                    continue

                meal_page_id = meal_rel[0].get("id")
                if not meal_page_id:
                    continue

                if meal_page_id not in meal_cache:
                    meal_page = self._get_page(meal_page_id)
                    if not meal_page:
                        continue
                    meal_name = self._notion_title(meal_page)
                    meal_type = self._notion_select(meal_page, "MealType")
                    meal_cache[meal_page_id] = (meal_name, meal_type)

                meal_name, meal_type = meal_cache[meal_page_id]
                if not meal_name or not meal_type:
                    continue

                # Map date -> dow
                dow = self._dow_from_date(date_only, week_start)
                if not dow:
                    continue

                # Map person to our helper suffix
                person_key = person.lower()
                if person_key not in ["michael", "lorna", "izzy"]:
                    continue

                meal_type_key = meal_type.lower()
                if meal_type_key not in ["dinner", "lunch", "breakfast"]:
                    # ignore smoothies/snacks/etc for now
                    continue

                self._set_ha_helper(meal_type_key, dow, person_key, meal_name)

            self.log("MealPlanner v1 recalculated")

        except Exception as e:
            self.error(f"Sync from Notion failed: {e}")

    def _dow_from_date(self, yyyy_mm_dd, week_start):
        # returns mon..sun if date is inside this week, else None
        try:
            y = int(yyyy_mm_dd[0:4])
            m = int(yyyy_mm_dd[5:7])
            d = int(yyyy_mm_dd[8:10])
            dt = self.date(y, m, d)
        except Exception:
            return None

        delta = (dt - week_start).days
        if delta < 0 or delta > 6:
            return None
        return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][delta]

    # ---------------------------
    # HA -> Notion upsert
    # ---------------------------

    def _on_ha_meal_changed(self, entity, attribute, old, new, kwargs):
        # ignore startup noise + our own writes
        if new is None or new == old:
            return
        if new.strip() in ["", "—"]:
            # don't write blanks to Notion
            return
        if self._ignore_ha_events_until and self.datetime() < self._ignore_ha_events_until:
            return

        meal_type = kwargs["meal_type"]         # dinner/lunch/breakfast
        dow = kwargs["dow"]                     # mon..sun
        person = kwargs["person"]               # michael/lorna/izzy
        person_title = person.capitalize()      # Notion select name expected

        now = self.datetime()
        week_start = self._week_start(now)
        target_date = self._date_for_dow(week_start, dow)
        date_iso = str(target_date)

        # We create a stable unique title so we can upsert
        # (Plan db doesn't show meal type as a column, so title is used to disambiguate)
        plan_title = f"{person_title} {meal_type.capitalize()} {date_iso}"

        # 1) find Meal page id from Meals DB for this (name + MealType)
        meal_page_id = self._find_meal_page_id(new, meal_type)
        if not meal_page_id:
            self.error(f"Could not find meal in Notion Meals DB: '{new}' ({meal_type})")
            return

        # 2) find existing Plan page by title
        existing_plan_page_id = self._find_plan_page_id(plan_title)

        props = {
            "Name": {"title": [{"type": "text", "text": {"content": plan_title}}]},
            "date": {"date": {"start": date_iso}},
            "person": {"select": {"name": person_title}},
            "meal": {"relation": [{"id": meal_page_id}]},
        }

        if existing_plan_page_id:
            self._update_page(existing_plan_page_id, {"properties": props})
            self.log(f"Updated Notion Plan: {plan_title} -> {new}")
        else:
            payload = {
                "parent": {"database_id": self.db_plan},
                "properties": props,
            }
            self._create_page(payload)
            self.log(f"Created Notion Plan: {plan_title} -> {new}")

    def _find_meal_page_id(self, meal_name, meal_type):
        # Query Meals DB: title == meal_name AND MealType == meal_type
        payload = {
            "filter": {
                "and": [
                    {
                        "property": "Name",
                        "title": {"equals": meal_name},
                    },
                    {
                        "property": "MealType",
                        "select": {"equals": meal_type},
                    },
                ]
            },
            "page_size": 5,
        }
        res = self._query_database(self.db_meals, payload)
        if not res:
            return None
        results = res.get("results", [])
        if not results:
            return None
        return results[0].get("id")

    def _find_plan_page_id(self, plan_title):
        payload = {
            "filter": {
                "property": "Name",
                "title": {"equals": plan_title},
            },
            "page_size": 5,
        }
        res = self._query_database(self.db_plan, payload)
        if not res:
            return None
        results = res.get("results", [])
        if not results:
            return None
        return results[0].get("id")

    # ---------------------------
    # Notion property extractors
    # ---------------------------

    def _notion_title(self, page):
        try:
            props = page.get("properties", {})
            title_prop = props.get("Name", {}).get("title", [])
            if not title_prop:
                return None
            return "".join([t.get("plain_text", "") for t in title_prop]).strip()
        except Exception:
            return None

    def _notion_select(self, page, prop_name):
        try:
            props = page.get("properties", {})
            sel = props.get(prop_name, {}).get("select", None)
            if not sel:
                return None
            return sel.get("name", None)
        except Exception:
            return None
