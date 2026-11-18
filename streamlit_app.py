"""실행: python -m streamlit run streamlit_app.py"""

from copy import deepcopy
from html import escape
from pathlib import Path
import json

import pandas as pd
import streamlit as st

from fridge_logic import (
    ValidationError, EPS, MAX_SERVINGS, load_data, to_base, normalize_rows, read_inventory_csv,
    requirements_for, evaluate_recipe, recommend_recipes, plan_requirements,
    shopping_list, receive_stock, consume_plan_item, export_state, import_state,
)

BASE_DIR = Path(__file__).resolve().parent
PAGES = ("개요", "냉장고", "요리 찾기", "식단·장보기", "사용 안내")
st.set_page_config(page_title="냉장고 구조대", page_icon="🥕", layout="wide", initial_sidebar_state="expanded")


@st.cache_data(show_spinner=False)
def app_data():
    return load_data(BASE_DIR / "data")


try:
    CATALOG, RECIPES = app_data()
except ValidationError as error:
    st.error(str(error))
    st.stop()

RECIPE_MAP = {recipe["id"]: recipe for recipe in RECIPES}
INGREDIENT_NAMES = sorted(item["name"] for item in CATALOG.values())


def init_state():
    defaults = {"inventory": {}, "priorities": [], "plan": {}, "prices": {},
                "history": [], "revision": 0, "page": "개요", "notice": ""}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = deepcopy(value)


def state_json():
    return export_state(st.session_state.inventory, st.session_state.priorities,
                        st.session_state.plan, st.session_state.prices)


def commit_changes(message="", **changes):
    before = state_json()
    candidate = json.loads(before)
    candidate.update(changes)
    candidate["priorities"] = [k for k in candidate["priorities"] if candidate["inventory"].get(k, 0) > EPS]
    checked = import_state(json.dumps(candidate, ensure_ascii=False, allow_nan=False), CATALOG, RECIPES)
    if json.loads(before) != checked:
        st.session_state.history = (st.session_state.history + [before])[-10:]
        for key in ("inventory", "priorities", "plan", "prices"):
            st.session_state[key] = checked[key]
        st.session_state.revision += 1
    st.session_state.notice = message


def undo():
    if st.session_state.history:
        checked = import_state(st.session_state.history[-1], CATALOG, RECIPES)
        st.session_state.history = st.session_state.history[:-1]
        for key in ("inventory", "priorities", "plan", "prices"):
            st.session_state[key] = checked[key]
        st.session_state.revision += 1
        st.session_state.notice = "최근 변경을 되돌렸어요."


def goto(page):
    st.session_state.page = page


def use_demo():
    stock = {"rice": 800, "egg": 6, "onion": 300, "carrot": 150, "green_onion": 100,
             "kimchi": 250, "tofu": 300, "ham": 150, "soy_sauce": 100, "cooking_oil": 100,
             "salt": 20, "sugar": 40, "sesame_oil": 50, "garlic": 80, "black_pepper": 10,
             "potato": 500, "noodle": 200, "butter": 40, "milk": 250, "cheese": 80}
    stock = {k: v for k, v in stock.items() if k in CATALOG}
    commit_changes("예시 냉장고를 불러왔어요. 요리 찾기에서 추천을 확인해 보세요.",
                   inventory=stock, priorities=[k for k in ("onion", "tofu") if k in stock], plan={})


def clear_fridge():
    commit_changes("냉장고를 비웠어요. 저장한 식단의 장보기 목록도 새 재고로 계산합니다.", inventory={}, priorities=[])


def fmt(value):
    return f"{value:,.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{value:,.0f}"


def money(value):
    return f"{value:,.0f}원"


def ingredient_label(key):
    return CATALOG[key]["name"]


def csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8-sig")


def stock_frame():
    rows = [{"ingredient": CATALOG[key]["name"], "quantity": float(value),
             "unit": CATALOG[key]["unit"], "priority": key in st.session_state.priorities}
            for key, value in sorted(st.session_state.inventory.items(), key=lambda x: CATALOG[x[0]]["name"])]
    return pd.DataFrame(rows, columns=["ingredient", "quantity", "unit", "priority"]).astype(
        {"ingredient": "str", "quantity": "float64", "unit": "str", "priority": "bool"})


def inject_style():
    st.markdown("""
    <style>
    .stApp {background:#f6f7f1; color:#233d35;}
    [data-testid="stSidebar"] {background:#eaf1e5; border-right:1px solid #dbe5d4;}
    [data-testid="stHeader"] {background:rgba(246,247,241,.9);}
    .block-container {padding-top:2.1rem; padding-bottom:3rem; max-width:1320px;}
    h1,h2,h3 {letter-spacing:-.035em;}
    .hero {padding:2rem 2.2rem; border:1px solid #d7e6d7; border-radius:22px;
           background:linear-gradient(120deg,#e1f0df,#faf1dc); margin-bottom:1.4rem;}
    .hero .eyebrow {font-size:.75rem; letter-spacing:.16em; font-weight:700; color:#467260;}
    .hero h1 {font-size:2.8rem; line-height:1.24; margin:.6rem 0; color:#204c3b;}
    .hero p {max-width:760px; color:#526a5e; margin-bottom:0; line-height:1.8;}
    .step {border-radius:16px; border:1px solid #e0e6da; background:#fffef9; padding:1.2rem; min-height:142px;}
    .step b {color:#276449; display:block; margin:.35rem 0; font-size:1.06rem;}
    .step p {font-size:.9rem; color:#657569; line-height:1.7; margin:0;}
    [data-testid="stMetric"] {background:#fffef9; border:1px solid #e0e6da; border-radius:15px; padding:1rem;}
    [data-testid="stMetricValue"] {color:#24614a;}
    div.stButton>button,div.stDownloadButton>button {border-radius:10px;}
    .recipe-top {font-size:.78rem; letter-spacing:.03em; color:#7b8174; margin-bottom:.2rem;}
    .recipe-title {font-weight:750; font-size:1.25rem; color:#274c3d; margin:.3rem 0 .4rem;}
    .pill {display:inline-block; border-radius:20px; font-size:.76rem; padding:.2rem .65rem;
           margin:.15rem .2rem .35rem 0; background:#e9f3e5; color:#386446;}
    .pill-warm {background:#faecd6; color:#906433;}
    @media(max-width:700px) {.hero{padding:1.35rem}.hero h1{font-size:2rem}.block-container{padding-top:1.2rem}}
    </style>
    """, unsafe_allow_html=True)


def sidebar():
    with st.sidebar:
        st.markdown("## 🥕 냉장고 구조대")
        st.caption("있는 재료부터, 맛있는 한 끼로")
        st.radio("메뉴", PAGES, key="page")
        st.divider()
        st.markdown("**내 데이터 보관하기**")
        st.caption("입력은 현재 브라우저 세션에 보관됩니다. 새로고침·연결 종료에 대비해 백업을 내려받으세요.")
        st.download_button("백업 JSON 저장", state_json(), "fridge_backup.json", "application/json", use_container_width=True)
        st.button("최근 변경 되돌리기", on_click=undo, disabled=not st.session_state.history, use_container_width=True)
        st.caption("최근 10회 변경까지 되돌릴 수 있어요.")
        st.divider()
        st.caption(f"직접 구성한 예시 레시피 {len(RECIPES)}개")


def overview():
    st.markdown("""
    <section class="hero">
      <div class="eyebrow">FRIDGE RESCUE · 오늘의 한 끼 구조 작전</div>
      <h1>냉장고에 있는 재료로<br>무엇을 만들까요?</h1>
      <p>재료와 수량을 기록하고, 만들 수 있는 요리를 찾아보세요.
      여러 요리를 골라도 필요한 재료를 한 번에 계산해 꼭 부족한 만큼만 장보기 목록에 모아드립니다.</p>
    </section>
    """, unsafe_allow_html=True)
    a, b, _ = st.columns([1.2, 1.2, 2])
    a.button("예시 냉장고로 체험", on_click=use_demo, type="primary", use_container_width=True)
    b.button("내 냉장고 입력하기", on_click=goto, args=("냉장고",), use_container_width=True)
    st.caption("예시 체험은 현재 냉장고와 식단을 예시 상태로 바꿉니다. 최근 변경 되돌리기로 복원할 수 있어요.")

    evaluations = recommend_recipes(RECIPES, st.session_state.inventory, CATALOG, priority=st.session_state.priorities)
    shopping = shopping_list(RECIPES, st.session_state.plan, st.session_state.inventory, CATALOG, st.session_state.prices)
    metrics = st.columns(4)
    metrics[0].metric("냉장고 재료", f"{len(st.session_state.inventory)}종")
    metrics[1].metric("바로 가능한 요리 · 2인분", f"{sum(x['can_cook'] for x in evaluations)}개")
    metrics[2].metric("식단에 담은 요리", f"{len(st.session_state.plan)}개")
    metrics[3].metric("예상 장보기 비용", money(sum(x["cost"] for x in shopping)))
    st.caption("바로 가능한 요리는 필수 재료가 모두 충분한 경우입니다. 예상 비용에는 수정 가능한 예시 단가를 사용합니다.")
    st.write("")
    cols = st.columns(3)
    for col, number, title, body in zip(cols, ("01", "02", "03"),
                                      ("재료를 기록해요", "먹고 싶은 요리를 골라요", "부족한 재료만 장봐요"),
                                      ("g·ml·개 단위로 입력하고 먼저 쓸 재료를 표시하세요.",
                                       "인분·시간·제외 재료를 바꿔 나에게 맞는 요리를 찾아보세요.",
                                       "여러 요리에 필요한 양을 모아 재고를 빼고, 구매·조리 후 재고도 갱신하세요.")):
        col.markdown(f'<div class="step">{number}<b>{title}</b><p>{body}</p></div>', unsafe_allow_html=True)
    st.write("")
    if st.session_state.inventory:
        left, right = st.columns(2)
        with left:
            st.subheader("냉장고 재료 구성")
            counts = {}
            for key in st.session_state.inventory:
                category = CATALOG[key].get("category", "기타")
                counts[category] = counts.get(category, 0) + 1
            frame = pd.DataFrame([{"분류": k, "재료 종류 수": v} for k, v in counts.items()])
            st.bar_chart(frame, x="분류", y="재료 종류 수", color="#4f8b68")
            st.caption("수량 단위가 다른 재료는 더하지 않고, 재료 종류 수를 비교합니다.")
        with right:
            st.subheader("준비가 가까운 요리")
            frame = pd.DataFrame([{"요리": x["recipe"]["name"], "수량 충족률(%)": round(x["coverage"], 1)} for x in evaluations[:6]])
            st.bar_chart(frame, x="요리", y="수량 충족률(%)", color="#d9a45c")
            st.caption("필수 재료마다 필요한 양 중 가진 양의 비율을 계산한 평균입니다.")
    else:
        st.info("처음이라면 ‘예시 냉장고로 체험’을 눌러 보세요. 재료 입력부터 장보기까지 흐름을 확인할 수 있어요.")


def inventory_page():
    st.title("🧺 내 냉장고")
    st.write("재료를 추가하고, 먼저 쓰고 싶은 재료를 표시해 주세요.")
    with st.container(border=True):
        st.subheader("재료 하나 추가하기")
        cols = st.columns([3, 2, 1.5])
        key = cols[0].selectbox("재료", sorted(CATALOG, key=ingredient_label), format_func=ingredient_label, key="add_ingredient")
        default = 1.0 if CATALOG[key]["unit"] == "개" else 100.0
        quantity = cols[1].number_input("추가할 수량", min_value=0.01, max_value=1000000.0, value=default,
                                        key=f"add_quantity_{key}", step=1.0)
        units = {"g": ("g", "kg"), "ml": ("ml", "L"), "개": ("개",)}[CATALOG[key]["unit"]]
        unit = cols[2].selectbox("단위", units, key=f"add_unit_{key}")
        st.caption(f"{CATALOG[key]['name']}의 기본 단위는 {CATALOG[key]['unit']}입니다. 같은 재료를 추가하면 수량이 합쳐집니다.")
        if st.button("냉장고에 추가", type="primary"):
            try:
                stock = receive_stock(st.session_state.inventory, {key: to_base(quantity, unit, key, CATALOG)}, CATALOG)
                commit_changes("재료를 추가했어요.", inventory=stock)
                st.rerun()
            except ValidationError as error:
                st.error(str(error))

    st.subheader("재고 한 번에 수정하기")
    st.caption("표의 수량을 바꾸거나 행을 추가·삭제한 뒤 ‘냉장고 저장’을 누르세요. 0으로 저장한 재료는 목록에서 빠집니다.")
    with st.form(f"stock_form_{st.session_state.revision}"):
        edited = st.data_editor(
            stock_frame(), num_rows="dynamic", hide_index=True, use_container_width=True,
            key=f"stock_editor_{st.session_state.revision}",
            column_config={
                "ingredient": st.column_config.SelectboxColumn("재료", options=INGREDIENT_NAMES, required=True),
                "quantity": st.column_config.NumberColumn("수량", min_value=0.0, max_value=1000000.0, format="%.2f", required=True),
                "unit": st.column_config.SelectboxColumn("단위", options=["g", "kg", "ml", "L", "개"], required=True),
                "priority": st.column_config.CheckboxColumn("먼저 사용", default=False),
            })
        if st.form_submit_button("냉장고 저장", type="primary"):
            try:
                stock, priorities = normalize_rows(edited.to_dict("records"), CATALOG)
                commit_changes("냉장고와 먼저 사용할 재료를 저장했어요.", inventory=stock, priorities=priorities)
                st.rerun()
            except ValidationError as error:
                st.error(str(error))
    st.caption("질량은 g↔kg, 부피는 ml↔L만 변환합니다. 달걀·식빵은 개 단위이며, 개↔g 변환은 하지 않습니다. 밥과 조리 전 쌀은 별도 재료입니다.")

    actions = st.columns(3)
    export = stock_frame().rename(columns={"ingredient": "재료", "quantity": "수량", "unit": "단위", "priority": "먼저 사용"})
    actions[0].download_button("재고 CSV 저장", csv_bytes(export), "fridge_inventory.csv", "text/csv", use_container_width=True)
    actions[1].button("예시 냉장고 불러오기", on_click=use_demo, use_container_width=True)
    actions[2].button("냉장고 비우기", on_click=clear_fridge, use_container_width=True)

    with st.expander("CSV로 재료 불러오기"):
        st.write("재료·수량·단위 열을 가진 CSV를 사용하세요. ‘먼저 사용’ 열에는 true/false를 쓸 수 있어요.")
        sample = pd.DataFrame([{"재료": "달걀", "수량": 4, "단위": "개", "먼저 사용": True},
                               {"재료": "양파", "수량": .3, "단위": "kg", "먼저 사용": False}])
        st.download_button("입력 예시 CSV", csv_bytes(sample), "inventory_sample.csv", "text/csv")
        upload = st.file_uploader("재고 CSV", type=["csv"], key="inventory_upload")
        mode = st.radio("적용 방식", ["현재 재고와 합치기", "CSV 내용으로 교체"], horizontal=True)
        if st.button("CSV 불러오기", disabled=upload is None):
            try:
                stock, priorities = read_inventory_csv(upload.getvalue(), CATALOG)
                if mode == "현재 재고와 합치기":
                    stock = receive_stock(st.session_state.inventory, stock, CATALOG) if stock else dict(st.session_state.inventory)
                    priorities = sorted(set(priorities) | set(st.session_state.priorities))
                commit_changes("CSV를 냉장고에 반영했어요.", inventory=stock, priorities=priorities)
                st.rerun()
            except ValidationError as error:
                st.error(f"CSV를 반영하지 못했어요: {error}")

    with st.expander("저장한 JSON 백업 복원하기"):
        st.caption("냉장고·우선 재료·식단·단가를 한 번에 복원합니다. 적용 후 최근 변경 되돌리기도 사용할 수 있어요.")
        upload = st.file_uploader("백업 JSON", type=["json"], key="backup_upload")
        if upload is not None:
            try:
                restored = import_state(upload.getvalue(), CATALOG, RECIPES)
                st.write(f"재료 {len(restored['inventory'])}종 · 요리 {len(restored['plan'])}개를 담은 백업입니다.")
                if st.button("이 백업으로 복원", type="primary"):
                    commit_changes("백업을 복원했어요.", **{k: restored[k] for k in ("inventory", "priorities", "plan", "prices")})
                    st.rerun()
            except ValidationError as error:
                st.error(str(error))


def update_priorities(widget_key):
    commit_changes(priorities=list(st.session_state[widget_key]))


def requirement_frame(evaluation):
    return pd.DataFrame([{
        "재료": CATALOG[key]["name"], "필요량": round(amount, 3),
        "보유량": round(st.session_state.inventory.get(key, 0), 3),
        "부족량": round(evaluation["missing"].get(key, 0), 3), "단위": CATALOG[key]["unit"],
    } for key, amount in evaluation["requirements"].items()])


def recipe_page():
    st.title("🍳 오늘 뭐 먹지?")
    st.write("내 재료의 수량까지 살펴보고, 지금 가능한 요리와 조금만 장보면 되는 요리를 골라보세요.")
    controls = st.columns([1, 1.3, 1.2, 1.8])
    servings = controls[0].number_input("준비할 인분", min_value=1, max_value=MAX_SERVINGS, value=2, step=1, key="recipe_servings")
    max_minutes = controls[1].slider("최대 조리 시간(분)", 5, 120, 45, 5)
    category = controls[2].selectbox("종류", ["전체", *sorted({r['category'] for r in RECIPES})])
    sorts = {"바로 가능한 요리 우선": "ready", "먼저 쓸 재료 우선": "priority", "부족한 재료 적은 순": "missing", "조리 시간 짧은 순": "time"}
    order = controls[3].selectbox("추천 순서", list(sorts))
    left, right = st.columns(2)
    priority_key = f"search_priority_{st.session_state.revision}"
    priority = left.multiselect("먼저 쓰고 싶은 재료", sorted(st.session_state.inventory, key=ingredient_label),
                               default=st.session_state.priorities, format_func=ingredient_label,
                               key=priority_key, on_change=update_priorities, args=(priority_key,))
    excluded = right.multiselect("빼고 싶은 재료", sorted(CATALOG, key=ingredient_label), format_func=ingredient_label)
    search = st.text_input("요리명·재료명 검색", placeholder="예: 달걀, 볶음밥, 두부")
    ready_only = st.checkbox("지금 가진 재료로 만들 수 있는 요리만 보기")
    results = recommend_recipes(RECIPES, st.session_state.inventory, CATALOG, servings=servings,
                               priority=priority, exclude=excluded, max_minutes=max_minutes,
                               category=category, search=search, sort_by=sorts[order])
    if ready_only:
        results = [result for result in results if result["can_cook"]]
    st.caption(f"조건에 맞는 요리 {len(results)}개 · ‘제외 재료’는 등록된 레시피 재료를 기준으로 걸러냅니다.")
    if not results:
        st.info("조건에 맞는 요리가 없어요. 시간·종류·제외 재료 조건을 조정하거나 냉장고에 재료를 추가해 보세요.")
        return
    if not st.session_state.inventory:
        st.info("냉장고가 비어 있어요. 요리를 먼저 식단에 담아 장보기 목록을 만들 수도 있어요.")
    page_count = (len(results) + 5) // 6
    page = st.selectbox("결과 페이지", range(1, page_count + 1), format_func=lambda x: f"{x} / {page_count}", key=f"recipe_page_{page_count}")
    visible = results[(page - 1) * 6:page * 6]
    for start in range(0, len(visible), 2):
        columns = st.columns(2)
        for column, result in zip(columns, visible[start:start + 2]):
            recipe = result["recipe"]
            with column, st.container(border=True):
                st.markdown(f'<div class="recipe-top">{escape(recipe["category"])} · {recipe["minutes"]:g}분 · {servings}인분</div>'
                            f'<div class="recipe-title">{escape(recipe["name"])}</div>', unsafe_allow_html=True)
                status = "바로 만들 수 있어요" if result["can_cook"] else f"{result['missing_count']}가지 재료가 부족해요"
                css = "pill" if result["can_cook"] else "pill pill-warm"
                st.markdown(f'<span class="{css}">{status}</span><span class="pill">우선 재료 {result["priority_count"]}종 활용</span>', unsafe_allow_html=True)
                st.write(recipe["description"])
                st.progress(min(1.0, max(0.0, result["coverage"] / 100)), text=f"수량 충족률 {result['coverage']:.0f}%")
                if result["missing"]:
                    brief = " · ".join(f"{CATALOG[k]['name']} {fmt(q)}{CATALOG[k]['unit']}" for k, q in result["missing"].items())
                    st.caption("부족한 재료: " + brief)
                with st.expander("재료와 조리 순서"):
                    st.dataframe(requirement_frame(result), hide_index=True, use_container_width=True)
                    st.caption(f"재료 표는 선택한 {servings}인분 기준입니다. 조리 문장은 기본 {recipe['base_servings']}인분 기준이므로 물 등 문장 속 분량도 맞춰 조절하세요.")
                    for number, step in enumerate(recipe["steps"], 1):
                        st.write(f"{number}. {step}")
                if st.button(f"식단에 {servings}인분 담기", key=f"add_plan_{recipe['id']}", use_container_width=True):
                    plan = dict(st.session_state.plan)
                    total = plan.get(recipe["id"], 0) + servings
                    if total > MAX_SERVINGS:
                        st.error(f"같은 요리는 식단에 최대 {MAX_SERVINGS}인분까지 담을 수 있어요.")
                    else:
                        plan[recipe["id"]] = total
                        commit_changes(f"{recipe['name']} {servings}인분을 식단에 담았어요. 같은 요리의 인분은 합쳐집니다.", plan=plan)
                        st.rerun()


def plan_page():
    st.title("🛒 식단과 장보기")
    st.write("요리를 여러 개 골라도 재고를 나눠 쓰도록, 전체 필요량을 합산해 계산합니다.")
    if not st.session_state.plan:
        st.info("아직 담은 요리가 없어요. 요리 찾기에서 먹고 싶은 메뉴를 식단에 담아주세요.")
        st.button("요리 찾으러 가기", on_click=goto, args=("요리 찾기",), type="primary")
        return
    st.subheader("이번에 준비할 요리")
    for recipe_id, servings in list(st.session_state.plan.items()):
        recipe = RECIPE_MAP[recipe_id]
        with st.container(border=True):
            cols = st.columns([3, 1.4, 1, 1.3])
            cols[0].markdown(f"**{recipe['name']}**")
            cols[0].caption(f"{recipe['category']} · 조리 예시 {recipe['minutes']:g}분")
            value = cols[1].number_input("인분", min_value=1, max_value=MAX_SERVINGS, value=servings,
                                        step=1, key=f"plan_servings_{recipe_id}_{st.session_state.revision}")
            if cols[2].button("수정", key=f"update_{recipe_id}", use_container_width=True):
                plan = dict(st.session_state.plan)
                plan[recipe_id] = value
                commit_changes("식단 인분을 수정했어요.", plan=plan)
                st.rerun()
            if cols[2].button("빼기", key=f"remove_{recipe_id}", use_container_width=True):
                plan = dict(st.session_state.plan)
                del plan[recipe_id]
                commit_changes("요리를 식단에서 뺐어요.", plan=plan)
                st.rerun()
            possible = evaluate_recipe(recipe, st.session_state.inventory, servings)["can_cook"]
            if cols[3].button("조리 완료", key=f"cook_{recipe_id}", disabled=not possible, use_container_width=True):
                try:
                    stock, plan = consume_plan_item(RECIPES, st.session_state.plan, recipe_id, st.session_state.inventory)
                    commit_changes(f"{recipe['name']} {servings}인분의 재료를 차감하고 식단에서 완료했어요.", inventory=stock, plan=plan)
                    st.rerun()
                except ValidationError as error:
                    st.error(str(error))
            cols[3].caption("저장된 인분 기준" if possible else "필수 재료 부족")
    st.caption("인분을 바꾼 뒤 ‘수정’으로 저장하세요. ‘조리 완료’는 저장된 인분의 재료를 차감합니다. 완료할 때마다 다른 요리의 가능 여부도 다시 계산합니다.")

    shopping = shopping_list(RECIPES, st.session_state.plan, st.session_state.inventory, CATALOG, st.session_state.prices)
    needs = plan_requirements(RECIPES, st.session_state.plan)
    total = sum(row["cost"] for row in shopping)
    cols = st.columns(3)
    cols[0].metric("전체 필요 재료", f"{len(needs)}종")
    cols[1].metric("장볼 재료", f"{len(shopping)}종")
    cols[2].metric("예상 구매 비용", money(total))
    st.subheader("통합 장보기 목록")
    st.caption("전체 요리의 필요량 합계 − 현재 재고 = 부족량입니다. 구매량은 g·ml·개 기준으로 올림하며, 가격은 실제 시세가 아닌 수정 가능한 가정 단가입니다.")
    if not shopping:
        st.success("모든 요리에 필요한 필수 재료가 충분해요. 준비가 끝난 요리를 ‘조리 완료’로 처리해 주세요.")
    else:
        frame = pd.DataFrame([{
            "구매 완료": False, "재료": row["name"], "필요량 합계": round(row["required"], 3),
            "보유량": round(row["available"], 3), "부족량": round(row["missing"], 3),
            "구매량": row["buy_quantity"], "단위": row["unit"], "가정 단가(원/기본단위)": row["unit_price"],
            "예상 금액(원)": row["cost"],
        } for row in shopping])
        with st.form(f"shopping_form_{st.session_state.revision}"):
            checked = st.data_editor(frame, hide_index=True, use_container_width=True,
                                     disabled=[c for c in frame.columns if c != "구매 완료"],
                                     column_config={"구매 완료": st.column_config.CheckboxColumn("구매 완료", default=False)},
                                     key=f"shopping_editor_{st.session_state.revision}")
            if st.form_submit_button("체크한 구매량을 재고에 반영", type="primary"):
                purchases = {row["ingredient"]: row["buy_quantity"] for row, flag in zip(shopping, checked["구매 완료"].tolist()) if flag}
                try:
                    stock = receive_stock(st.session_state.inventory, purchases, CATALOG)
                    commit_changes(f"구매한 재료 {len(purchases)}종을 냉장고에 더했어요.", inventory=stock)
                    st.rerun()
                except ValidationError as error:
                    st.error(str(error))
        st.download_button("장보기 목록 CSV 저장", csv_bytes(frame.drop(columns=["구매 완료"])), "shopping_list.csv", "text/csv")
        chart = pd.DataFrame([{"재료": row["name"], "예상 금액(원)": row["cost"]} for row in shopping])
        st.bar_chart(chart, x="재료", y="예상 금액(원)", color="#d6a35e")

    with st.expander("가정 단가 수정하기"):
        st.caption("가격은 계산 기능을 체험하기 위한 예시입니다. 실제 구매 예정인 가격으로 바꿔보세요. g·ml·개 기본 단위당 가격이며 포장 단위는 반영하지 않습니다.")
        prices = pd.DataFrame([{"ingredient": key, "재료": CATALOG[key]["name"], "기본 단위": CATALOG[key]["unit"],
                                "단가(원)": float(st.session_state.prices.get(key, CATALOG[key]["price"]))} for key in sorted(needs, key=ingredient_label)])
        with st.form(f"price_form_{st.session_state.revision}"):
            edited = st.data_editor(prices.drop(columns=["ingredient"]), hide_index=True, use_container_width=True,
                                    disabled=["재료", "기본 단위"],
                                    column_config={"단가(원)": st.column_config.NumberColumn("단가(원/기본단위)", min_value=0.0, max_value=1000000.0, format="%.2f", required=True)},
                                    key=f"price_editor_{st.session_state.revision}")
            if st.form_submit_button("단가 저장"):
                updated = dict(st.session_state.prices)
                for key, price in zip(prices["ingredient"], edited["단가(원)"]):
                    updated[key] = price
                try:
                    commit_changes("가정 단가를 저장했어요.", prices=updated)
                    st.rerun()
                except (ValidationError, ValueError) as error:
                    st.error(str(error))

    with st.expander("전체 식단의 재료 계산 보기"):
        rows = [{"재료": CATALOG[key]["name"], "전체 필요량": round(amount, 3),
                 "현재 재고": round(st.session_state.inventory.get(key, 0), 3), "단위": CATALOG[key]["unit"]} for key, amount in needs.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def guide_page():
    st.title("📖 사용 안내")
    st.markdown("""
    ### 한 끼를 준비하는 순서
    1. **냉장고**에서 가진 재료와 수량을 입력합니다. 표에서 먼저 사용할 재료를 체크할 수 있어요.
    2. **요리 찾기**에서 인분·종류·시간을 선택하고 필요한 재료를 확인합니다.
    3. 먹고 싶은 요리를 **식단에 담기**로 모읍니다. 같은 요리는 인분이 더해집니다.
    4. **식단·장보기**에서 부족한 재료를 확인하고 실제로 구매한 항목을 체크해 재고에 반영합니다.
    5. 요리를 만든 뒤 **조리 완료**를 누르면 해당 분량의 재료와 식단 항목을 정리합니다.

    ### 계산을 읽는 방법
    - **수량 충족률**: 필수 재료마다 ‘보유량 ÷ 필요량’을 최대 100%로 계산한 뒤 평균을 냅니다.
      g·ml·개처럼 다른 단위를 직접 더하지 않습니다.
    - **바로 가능한 요리**: 충족률을 반올림해 100%로 보이더라도, 필수 재료 중 부족한 것이 있으면 포함하지 않습니다.
    - **장보기 부족량**: 선택한 요리의 전체 필요량을 합산한 뒤 현재 재고를 한 번만 뺍니다.
    - **구매량과 예상 비용**: 부족량을 기본 단위로 올림하고 가정 단가를 곱합니다.
      포장 단위, 매장별 가격, 할인은 계산하지 않습니다.
    - **기본 양념**: 소금·간장·식용유 등도 필수 재료에 포함됩니다. 물은 재고 계산에서 제외합니다.
    - **인분**: 재료 표는 선택한 인분에 맞춰 계산합니다. 조리 문장은 기본 2인분 기준입니다.

    ### 내 데이터 보관
    입력은 현재 브라우저의 Streamlit 세션에서 관리합니다. 사이드바의 **백업 JSON 저장**으로 내려받고,
    냉장고 화면의 **저장한 JSON 백업 복원하기**에서 다시 불러오세요.
    최근 10회 변경은 **최근 변경 되돌리기**로 복원할 수 있습니다.

    ### 예시 데이터에 관하여
    레시피 30개와 재료 사전은 이 프로젝트를 위해 AI의 도움으로 직접 구성한 교육용 예시입니다.
    분량·시간·가격은 예시 기준이며, 실제 매장 시세나 영양 분석 자료가 아닙니다.
    ‘빼고 싶은 재료’는 레시피에 등록된 재료를 기준으로 제외하는 필터입니다.
    """)
    with st.expander("등록된 재료와 기본 단위"):
        st.dataframe(pd.DataFrame([{"재료": item["name"], "기본 단위": item["unit"], "분류": item.get("category", "기타")} for item in CATALOG.values()]),
                     hide_index=True, use_container_width=True)
    st.caption("냉장고 구조대 · 기말 프로젝트")


def main():
    init_state()
    inject_style()
    sidebar()
    if st.session_state.notice:
        st.success(st.session_state.notice)
        st.session_state.notice = ""
    routes = {"개요": overview, "냉장고": inventory_page, "요리 찾기": recipe_page,
              "식단·장보기": plan_page, "사용 안내": guide_page}
    routes[st.session_state.page]()


if __name__ == "__main__":
    main()
