"""냉장고 구조대의 수량 계산·추천·장보기·백업 검증.

화면과 계산을 분리해 Streamlit을 설치하지 않아도 핵심 규칙을 검사할 수 있다.
모든 수량은 재료 사전의 g / ml / 개 기준으로 계산한다.
"""

import json
import math
import csv
from io import StringIO
from pathlib import Path

EPS = 1e-9
MAX_QUANTITY = 100_000_000
MAX_SERVINGS = 40
MAX_BACKUP_BYTES = 1_000_000
UNIT_FACTORS = {"g": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "L": ("ml", 1000), "개": ("개", 1)}


class ValidationError(ValueError):
    """사용자가 입력을 수정하면 해결할 수 있는 오류."""


def _number(value, label="수량", allow_zero=True, maximum=MAX_QUANTITY):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValidationError(f"{label}: 올바른 숫자를 입력하세요.")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError(f"{label}: 올바른 숫자를 입력하세요.") from error
    if not math.isfinite(number) or number < 0 or (not allow_zero and number == 0) or number > maximum:
        raise ValidationError(f"{label}: {'0 이상' if allow_zero else '0 초과'} {maximum:g} 이하의 유한한 숫자를 입력하세요.")
    return number


def _servings(value):
    number = _number(value, "인분", False, MAX_SERVINGS)
    if number != int(number):
        raise ValidationError("인분은 정수로 입력하세요.")
    return int(number)


def _clean_name(value):
    return "".join(str(value).strip().lower().split())


def validate_catalog(raw):
    if not isinstance(raw, dict) or not raw:
        raise ValidationError("재료 사전이 비어 있거나 올바르지 않습니다.")
    result, names = {}, {}
    for key, item in raw.items():
        if not isinstance(key, str) or not key or not isinstance(item, dict):
            raise ValidationError("재료 ID와 재료 정보 형식을 확인하세요.")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValidationError(f"재료 이름이 없습니다: {key}")
        if item.get("unit") not in ("g", "ml", "개"):
            raise ValidationError(f"재료 기본 단위가 잘못되었습니다: {key}")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(x, str) for x in aliases):
            raise ValidationError(f"별칭 형식을 확인하세요: {key}")
        price = _number(item.get("price", 0), "기본 단가", maximum=1_000_000)
        clean = dict(item, name=item["name"].strip(), aliases=aliases, price=price)
        result[key] = clean
        for name in (key, clean["name"], *aliases):
            token = _clean_name(name)
            if not token or token in names and names[token] != key:
                raise ValidationError(f"재료 이름 또는 별칭이 중복되었습니다: {name}")
            names[token] = key
    return result


def validate_recipes(raw, catalog):
    if not isinstance(raw, list) or not raw:
        raise ValidationError("레시피 목록이 비어 있거나 올바르지 않습니다.")
    result, seen = [], set()
    for recipe in raw:
        if not isinstance(recipe, dict):
            raise ValidationError("레시피 형식을 확인하세요.")
        key = recipe.get("id")
        if not isinstance(key, str) or not key or key in seen:
            raise ValidationError("레시피 ID가 없거나 중복되었습니다.")
        seen.add(key)
        for field in ("name", "category", "description"):
            if not isinstance(recipe.get(field), str) or not recipe[field].strip():
                raise ValidationError(f"레시피 {field}를 확인하세요: {key}")
        base_servings = _servings(recipe.get("base_servings"))
        minutes = _number(recipe.get("minutes"), "조리 시간", False, 600)
        ingredients = recipe.get("ingredients")
        if not isinstance(ingredients, list) or not ingredients:
            raise ValidationError(f"필요 재료가 없습니다: {key}")
        required = 0
        for ingredient in ingredients:
            if not isinstance(ingredient, dict) or ingredient.get("ingredient") not in catalog:
                raise ValidationError(f"등록되지 않은 레시피 재료입니다: {key}")
            _number(ingredient.get("quantity"), "레시피 수량", False)
            if type(ingredient.get("optional", False)) is not bool:
                raise ValidationError(f"선택 재료 표시 형식을 확인하세요: {key}")
            required += not ingredient.get("optional", False)
        if not required:
            raise ValidationError(f"필수 재료가 필요합니다: {key}")
        if not isinstance(recipe.get("steps"), list) or not recipe["steps"] or any(not isinstance(s, str) or not s.strip() for s in recipe["steps"]):
            raise ValidationError(f"조리 순서를 확인하세요: {key}")
        if not isinstance(recipe.get("tags", []), list) or any(not isinstance(s, str) for s in recipe.get("tags", [])):
            raise ValidationError(f"태그 형식을 확인하세요: {key}")
        result.append(dict(recipe, base_servings=base_servings, minutes=minutes,
                           ingredients=[dict(item, quantity=_number(item["quantity"], "레시피 수량", False))
                                        for item in ingredients]))
    return result


def load_data(directory):
    directory = Path(directory)
    try:
        catalog = validate_catalog(json.loads((directory / "ingredients.json").read_text(encoding="utf-8")))
        recipes = validate_recipes(json.loads((directory / "recipes.json").read_text(encoding="utf-8")), catalog)
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError("data 폴더의 ingredients.json과 recipes.json을 확인하세요.") from error
    return catalog, recipes


def resolve_ingredient(name, catalog):
    token = _clean_name(name)
    for key, item in catalog.items():
        if token in {_clean_name(x) for x in (key, item["name"], *item.get("aliases", []))}:
            return key
    raise ValidationError(f"등록되지 않은 재료입니다: {name}")


def to_base(quantity, unit, ingredient_id, catalog):
    if ingredient_id not in catalog:
        raise ValidationError(f"등록되지 않은 재료입니다: {ingredient_id}")
    amount = _number(quantity)
    if unit not in UNIT_FACTORS:
        raise ValidationError("단위는 g, kg, ml, L, 개 중에서 선택하세요.")
    dimension, factor = UNIT_FACTORS[unit]
    if dimension != catalog[ingredient_id]["unit"]:
        raise ValidationError(f"{catalog[ingredient_id]['name']}: {catalog[ingredient_id]['unit']} 계열 단위를 사용하세요.")
    return _number(amount * factor)


def normalize_rows(rows, catalog):
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValidationError("재료 표는 500행 이내여야 합니다.")
    inventory, priorities = {}, set()
    for index, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict):
                raise ValidationError("행 형식을 확인하세요.")
            raw_name = row.get("ingredient", row.get("name", ""))
            # 새 빈 행만 건너뛰고, 수량이나 단위가 있는 미완성 행은 오류로 알립니다.
            if raw_name is None or isinstance(raw_name, str) and not raw_name.strip():
                quantity = row.get("quantity")
                if quantity in (None, "", 0, 0.0):
                    continue
                raise ValidationError("재료 이름을 선택하세요.")
            key = resolve_ingredient(raw_name, catalog)
            value = to_base(row.get("quantity"), row.get("unit", catalog[key]["unit"]), key, catalog)
            inventory[key] = _number(inventory.get(key, 0) + value)
            flag = row.get("priority", False)
            if isinstance(flag, str):
                if flag.strip().lower() not in ("true", "false", "1", "0", "예", "아니오", ""):
                    raise ValidationError("먼저 사용은 true/false로 입력하세요.")
                flag = flag.strip().lower() in ("true", "1", "예")
            elif type(flag) is not bool:
                raise ValidationError("먼저 사용은 체크 표시로 입력하세요.")
            if flag:
                priorities.add(key)
        except ValidationError as error:
            raise ValidationError(f"{index}행 · {error}") from error
    inventory = {key: value for key, value in inventory.items() if value > EPS}
    return inventory, sorted(priorities & inventory.keys())


def read_inventory_csv(content, catalog):
    """CSV 원본 헤더를 검사하여 중복 열이 조용히 사라지는 것을 막는다."""
    if not isinstance(content, (str, bytes)) or len(content.encode("utf-8") if isinstance(content, str) else content) > 200000:
        raise ValidationError("재고 CSV는 200KB 이내로 준비하세요.")
    try:
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content.lstrip("\ufeff")
        reader = csv.DictReader(StringIO(text), strict=True)
        if not reader.fieldnames:
            raise ValidationError("CSV에 재료·수량·단위 열이 필요합니다.")
        aliases = {"재료": "ingredient", "수량": "quantity", "단위": "unit", "먼저 사용": "priority", "먼저사용": "priority"}
        names = [aliases.get(name.strip(), name.strip()) for name in reader.fieldnames]
        if len(names) != len(set(names)):
            raise ValidationError("같은 뜻의 열이 중복되었습니다. 재료·수량·단위·먼저 사용 열을 각각 하나씩 사용하세요.")
        if not {"ingredient", "quantity", "unit"}.issubset(names):
            raise ValidationError("CSV의 재료·수량·단위 열을 확인하세요.")
        rows = []
        for row in reader:
            if None in row:
                raise ValidationError("CSV의 열 수가 헤더와 맞지 않습니다.")
            rows.append({name: row[original] for original, name in zip(reader.fieldnames, names)})
            if len(rows) > 500:
                raise ValidationError("재료 표는 500행 이내여야 합니다.")
        return normalize_rows(rows, catalog)
    except (UnicodeError, csv.Error) as error:
        raise ValidationError("UTF-8 형식의 올바른 CSV 파일을 선택하세요.") from error


def requirements_for(recipe, servings):
    factor = _servings(servings) / _servings(recipe["base_servings"])
    needs = {}
    for item in recipe["ingredients"]:
        if not item.get("optional", False):
            key = item["ingredient"]
            needs[key] = _number(needs.get(key, 0) + _number(item["quantity"], "필요량", False) * factor)
    return needs


def evaluate_recipe(recipe, inventory, servings, priority=()):
    needs = requirements_for(recipe, servings)
    stock = {key: _number(inventory.get(key, 0)) for key in needs}
    missing = {key: amount - stock[key] for key, amount in needs.items() if amount - stock[key] > EPS}
    coverage = sum(min(1, stock[key] / amount) for key, amount in needs.items()) / len(needs) * 100
    return {
        "id": recipe["id"], "recipe": recipe, "coverage": coverage,
        "missing_count": len(missing), "can_cook": not missing,
        "priority_count": sum(key in priority and stock[key] > EPS for key in needs),
        "requirements": needs, "missing": missing,
    }


def recommend_recipes(recipes, inventory, catalog, servings=2, priority=(), exclude=(), max_minutes=120, category="전체", search="", sort_by="ready"):
    _servings(servings)
    max_minutes = _number(max_minutes, "최대 조리 시간", False, 600)
    excluded = set(exclude)
    if any(key not in catalog for key in excluded):
        raise ValidationError("제외 재료를 확인하세요.")
    query = _clean_name(search)
    result = []
    for recipe in recipes:
        ids = {x["ingredient"] for x in recipe["ingredients"]}
        if ids & excluded or recipe["minutes"] > max_minutes or category != "전체" and recipe["category"] != category:
            continue
        haystack = _clean_name(recipe["name"] + " ".join(recipe.get("tags", [])) + " ".join(catalog[k]["name"] for k in ids))
        if query and query not in haystack:
            continue
        result.append(evaluate_recipe(recipe, inventory, servings, priority))
    if sort_by == "priority":
        key = lambda x: (-x["priority_count"], not x["can_cook"], -x["coverage"], x["recipe"]["minutes"], x["id"])
    elif sort_by == "missing":
        key = lambda x: (x["missing_count"], -x["coverage"], -x["priority_count"], x["recipe"]["minutes"], x["id"])
    elif sort_by == "time":
        key = lambda x: (x["recipe"]["minutes"], not x["can_cook"], -x["coverage"], x["id"])
    elif sort_by == "ready":
        key = lambda x: (not x["can_cook"], -x["priority_count"], -x["coverage"], x["missing_count"], x["recipe"]["minutes"], x["id"])
    else:
        raise ValidationError("정렬 방식을 확인하세요.")
    return sorted(result, key=key)


def _recipe_map(recipes):
    return {r["id"]: r for r in recipes}


def plan_requirements(recipes, plan):
    lookup = _recipe_map(recipes)
    if not isinstance(plan, dict) or len(plan) > len(lookup):
        raise ValidationError("식단 목록 형식이 올바르지 않습니다.")
    result = {}
    for key, servings in plan.items():
        if key not in lookup:
            raise ValidationError(f"식단에 등록되지 않은 요리가 있습니다: {key}")
        for ingredient, amount in requirements_for(lookup[key], servings).items():
            result[ingredient] = _number(result.get(ingredient, 0) + amount)
    return result


def shopping_list(recipes, plan, inventory, catalog, prices=None):
    needs = plan_requirements(recipes, plan)
    result, prices = [], prices or {}
    for key, required in needs.items():
        available = _number(inventory.get(key, 0))
        missing = max(0, required - available)
        if missing <= EPS:
            continue
        price = _number(prices.get(key, catalog[key].get("price", 0)), "단가", maximum=1_000_000)
        buy = math.ceil(missing - EPS)
        result.append({"ingredient": key, "name": catalog[key]["name"], "unit": catalog[key]["unit"],
                       "required": required, "available": available, "missing": missing,
                       "buy_quantity": buy, "unit_price": price, "cost": round(buy * price, 2)})
    return sorted(result, key=lambda x: (catalog[x["ingredient"]].get("category", ""), x["name"]))


def receive_stock(inventory, purchases, catalog):
    if not isinstance(purchases, dict) or not purchases:
        raise ValidationError("구매 완료한 재료를 먼저 선택하세요.")
    result = dict(inventory)
    for key, quantity in purchases.items():
        if key not in catalog:
            raise ValidationError(f"등록되지 않은 재료입니다: {key}")
        result[key] = _number(_number(result.get(key, 0)) + _number(quantity, "구매 수량", False))
    return result


def cook_recipe(recipe, servings, inventory):
    evaluation = evaluate_recipe(recipe, inventory, servings)
    if not evaluation["can_cook"]:
        raise ValidationError("필수 재료가 부족합니다. 장보기 또는 재고 수정을 먼저 해주세요.")
    result = dict(inventory)
    for key, quantity in evaluation["requirements"].items():
        remainder = max(0, result.get(key, 0) - quantity)
        if remainder <= EPS:
            result.pop(key, None)
        else:
            result[key] = remainder
    return result


def consume_plan_item(recipes, plan, recipe_id, inventory):
    lookup = _recipe_map(recipes)
    if recipe_id not in plan or recipe_id not in lookup:
        raise ValidationError("식단에 있는 요리만 완료 처리할 수 있습니다.")
    stock = cook_recipe(lookup[recipe_id], plan[recipe_id], inventory)
    updated = dict(plan)
    del updated[recipe_id]
    return stock, updated


def export_state(inventory, priorities, plan, prices):
    value = {"schema_version": 1, "inventory": inventory, "priorities": list(priorities), "plan": plan, "prices": prices}
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def import_state(text, catalog, recipes):
    if not isinstance(text, (str, bytes)) or len(text.encode("utf-8") if isinstance(text, str) else text) > MAX_BACKUP_BYTES:
        raise ValidationError("백업 파일은 1MB 이하여야 합니다.")
    try:
        value = json.loads(text)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError("올바른 JSON 백업 파일을 선택하세요.") from error
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValidationError("지원하는 백업 파일 형식이 아닙니다.")
    stock, plan, prices, priorities = (value.get(k) for k in ("inventory", "plan", "prices", "priorities"))
    if not isinstance(stock, dict) or len(stock) > len(catalog) or not isinstance(prices, dict) or len(prices) > len(catalog):
        raise ValidationError("재고 또는 단가 형식을 확인하세요.")
    inventory = {}
    for key, quantity in stock.items():
        if key not in catalog:
            raise ValidationError(f"백업에 등록되지 않은 재료가 있습니다: {key}")
        amount = _number(quantity)
        if amount > EPS:
            inventory[key] = amount
    if not isinstance(priorities, list) or len(priorities) > len(catalog) or any(not isinstance(k, str) or k not in inventory for k in priorities):
        raise ValidationError("우선 사용 재료는 현재 재고가 있는 재료여야 합니다.")
    plan_requirements(recipes, plan)
    checked_prices = {}
    for key, price in prices.items():
        if key not in catalog:
            raise ValidationError(f"백업의 단가 재료를 확인하세요: {key}")
        checked_prices[key] = _number(price, "단가", maximum=1_000_000)
    return {"schema_version": 1, "inventory": inventory, "priorities": sorted(set(priorities)),
            "plan": {k: _servings(v) for k, v in plan.items()}, "prices": checked_prices}
