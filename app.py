# ============================================================
# 나라장터 공사 공고 크롤러 (Streamlit 버전)
# - API: getBidPblancListInfoCnstwkPPSSrch
# - 날짜 + 공고명 + 업종명 + 참가제한지역코드 + 기초금액 범위 + 계약방법 필터
# - 기초금액 천단위 콤마, 컬럼 한글화
# - 결과 테이블 + 엑셀 다운로드
# - 링크 생성 기능은 전부 제거
# ============================================================

import os
import re
import json
from datetime import datetime, date

import requests
import pandas as pd
import streamlit as st

# ------------------------------------------------------------
# 0. Streamlit 기본 설정 & 스타일
# ------------------------------------------------------------
st.set_page_config(
    page_title="나라장터 공사공고 크롤러",
    page_icon="🏗️",
    layout="wide",
)

# 간단한 커스텀 CSS (헤더/테이블 가독성 강화)
st.markdown("""
<style>
/* 전체 폰트 사이즈 약간 줄이기 & 라인 간격 조정 */
html, body, [class*="css"]  {
    font-size: 14px;
}

/* 헤더 영역 여백 */
.block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
}

/* 표 헤더 진하게 */
thead tr th {
    font-weight: 700 !important;
}

/* 사이드바 제목 스타일 */
.sidebar .sidebar-content h2 {
    margin-top: 0.2rem;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# 1. 참가제한 지역코드 안내
# ------------------------------------------------------------
REGION_CODE_HELP = """
**참가제한 지역코드 예시**

- 11: 서울특별시 26: 부산광역시 27: 대구광역시 28: 인천광역시  
- 29: 광주광역시 30: 대전광역시 31: 울산광역시 36: 세종특별자치시  
- 41: 경기도   42: 강원도   43: 충청북도   44: 충청남도  
- 45: 전라북도  46: 전라남도  47: 경상북도  48: 경상남도  
- 50: 제주도   51: 강원특별자치도 52: 전북특별자치도  
- 99: 기타    00: 전국(지역제한 없음, 코드가 00인 공고만 조회)

※ 필터를 사용하지 않으려면 **빈칸**으로 두세요.
"""

BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoCnstwkPPSSrch"


# ------------------------------------------------------------
# 2. 공통 유틸 함수
# ------------------------------------------------------------
def get_service_key() -> str:
    """
    SERVICE_KEY 우선순위:
    1) st.secrets["SERVICE_KEY"]
    2) 환경변수 SERVICE_KEY
    3) (없으면 빈 문자열)
    """
    key = ""
    try:
        key = st.secrets.get("SERVICE_KEY", "")
    except Exception:
        pass

    if not key:
        key = os.getenv("SERVICE_KEY", "")

    return key


def safe_get_items(json_data: dict):
    """response.body.items 에서 item 리스트만 안전하게 꺼내기"""
    try:
        response = json_data.get("response", {})
        body = response.get("body", {})
        items = body.get("items")

        if not items:
            return []

        if isinstance(items, list):
            return items

        if isinstance(items, dict):
            item = items.get("item")
            if isinstance(item, list):
                return item
            if isinstance(item, dict):
                return [item]

        return []
    except Exception:
        return []


def normalize_date_str(d) -> str:
    """date 또는 문자열을 YYYY-MM-DD 문자열로 통일"""
    if d is None or d == "":
        return ""
    if isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    return str(d).strip()


def parse_money(val: str):
    """콤마/공백이 섞인 문자열을 숫자로 변환. 비어있으면 None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    s = re.sub(r"[^\d]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


# ------------------------------------------------------------
# 3. 핵심 검색 함수 (Streamlit에서 호출)
# ------------------------------------------------------------
def search_bids(
    service_key: str,
    start_date,
    end_date,
    inqry_div,
    bid_name,
    industry_name,
    region_code,
    min_price,
    max_price,
    contract_filter,
    page_no,
    num_rows,
):
    log_lines = []

    if not service_key:
        return "❌ SERVICE_KEY가 설정되지 않았습니다.", pd.DataFrame()

    # 날짜 처리
    start_str = normalize_date_str(start_date)
    end_str = normalize_date_str(end_date)

    inqry_bgn = start_str.replace("-", "") + "0000" if start_str else ""
    inqry_end = end_str.replace("-", "") + "2359" if end_str else ""

    params = {
        "serviceKey": service_key,
        "pageNo": str(page_no),
        "numOfRows": str(num_rows),
        "inqryDiv": str(inqry_div),
        "type": "json",
    }

    if inqry_bgn:
        params["inqryBgnDt"] = inqry_bgn
    if inqry_end:
        params["inqryEndDt"] = inqry_end
    if bid_name:
        params["bidNtceNm"] = bid_name.strip()
    if industry_name:
        params["indstrytyNm"] = industry_name.strip()

    # 참가제한 지역코드 필터 (prtcptLmtRgnCd)
    region_code = str(region_code).strip()
    if region_code:
        if len(region_code) == 1:
            region_code = "0" + region_code
        params["prtcptLmtRgnCd"] = region_code

    try:
        resp = requests.get(BASE_URL, params=params, timeout=10)
        log_lines.append("📎 나라장터 API 요청 완료")

        if resp.status_code != 200:
            log_lines.append(f"❌ HTTP 오류: {resp.status_code}")
            return "\n".join(log_lines), pd.DataFrame()

        try:
            data = resp.json()
        except json.JSONDecodeError:
            log_lines.append("❌ JSON 파싱 실패")
            log_lines.append(resp.text[:200])
            return "\n".join(log_lines), pd.DataFrame()

        header = data.get("response", {}).get("header", {})
        code = header.get("resultCode")
        msg = header.get("resultMsg")
        log_lines.append(f"API 응답 코드: {code}, 메시지: {msg}")

        if code != "00":
            log_lines.append("❌ 조건 불충족 또는 파라미터 오류")
            return "\n".join(log_lines), pd.DataFrame()

        items = safe_get_items(data)
        if not items:
            log_lines.append("⚠ 검색 조건에 해당하는 데이터 없음")
            return "\n".join(log_lines), pd.DataFrame()

        df = pd.json_normalize(items)

        # 🔢 기초금액 숫자 컬럼 생성 후 범위 필터
        if "presmptPrce" in df.columns:
            df["_presmpt_num"] = pd.to_numeric(
                df["presmptPrce"].astype(str).str.replace(r"[^\d]", "", regex=True),
                errors="coerce"
            ).fillna(0)
        else:
            df["_presmpt_num"] = 0

        min_val = parse_money(min_price)
        max_val = parse_money(max_price)

        if min_val is not None:
            df = df[df["_presmpt_num"] >= min_val]
            log_lines.append(f"🔻 최소 기초금액 이상 필터: {min_val:,.0f}원")
        if max_val is not None:
            df = df[df["_presmpt_num"] <= max_val]
            log_lines.append(f"🔺 최대 기초금액 이하 필터: {max_val:,.0f}원")

        # 🧾 계약방법 필터 (cntrctCnclsMthdNm)
        if "cntrctCnclsMthdNm" in df.columns:
            if contract_filter == "only_private":
                df = df[df["cntrctCnclsMthdNm"].astype(str).str.contains("수의", na=False)]
                log_lines.append("✅ 계약방법 필터: 수의계약만")
            elif contract_filter == "exclude_private":
                df = df[~df["cntrctCnclsMthdNm"].astype(str).str.contains("수의", na=False)]
                log_lines.append("✅ 계약방법 필터: 수의계약 제외")
            else:
                log_lines.append("✅ 계약방법 필터: 전체")
        else:
            log_lines.append("⚠ cntrctCnclsMthdNm 컬럼 없음 (계약방법 필터 미적용)")

        if df.empty:
            log_lines.append("⚠ 필터 적용 후 남은 공고 없음")
            return "\n".join(log_lines), pd.DataFrame()

        # 표시할 컬럼 정의
        prefer_cols = [
            "bidNtceNo",        # 공고번호
            "bidNtceOrd",       # 공고차수
            "bidNtceNm",        # 공고명
            "ntceInsttNm",      # 공고기관명
            "pblancDate",       # 공고게시일시
            "opengDt",          # 개찰일시
            "indstrytyNm",      # 업종명
            "presmptPrce",      # 기초금액(문자)
            "prtcptLmtRgnCd",   # 참가제한지역코드
            "prtcptLmtRgnNm",   # 참가제한지역명
            "cntrctCnclsMthdNm" # 계약체결방법명
        ]

        exist = [c for c in prefer_cols if c in df.columns]
        df_view = df[exist].copy()

        # 기초금액 천단위 콤마
        if "presmptPrce" in df_view.columns:
            df_view["presmptPrce"] = (
                df["_presmpt_num"]
                .astype(float)
                .apply(lambda x: f"{int(x):,}")
            )

        # 컬럼명 한글화
        col_map = {
            "bidNtceNo": "공고번호",
            "bidNtceOrd": "공고차수",
            "bidNtceNm": "공고명",
            "ntceInsttNm": "공고기관",
            "pblancDate": "공고게시일시",
            "opengDt": "개찰일시",
            "indstrytyNm": "업종명",
            "presmptPrce": "기초금액",
            "prtcptLmtRgnCd": "참가제한지역코드",
            "prtcptLmtRgnNm": "참가제한지역명",
            "cntrctCnclsMthdNm": "계약방법",
        }
        df_view.rename(
            columns={k: v for k, v in col_map.items() if k in df_view.columns},
            inplace=True
        )

        log_lines.append(f"📊 공고 건수(모든 필터 적용 후): {len(df_view)}건")

        return "\n".join(log_lines), df_view

    except Exception as e:
        log_lines.append(f"💥 예외 발생: {e}")
        return "\n".join(log_lines), pd.DataFrame()


# ------------------------------------------------------------
# 4. Streamlit UI 구성
# ------------------------------------------------------------
def main():
    st.title("🏗️ 나라장터 공사공고 크롤러")
    st.caption("getBidPblancListInfoCnstwkPPSSrch · 공사 공고 필터 조회 · Streamlit 버전")

    # --- 사이드바: 필터 입력 영역 ---
    with st.sidebar:
        st.header("🔧 검색 조건")

        # 서비스키 표시 및 입력 보조
        service_key = get_service_key()
        if not service_key:
            st.error("SERVICE_KEY 가 설정되어 있지 않습니다. "
                     "`st.secrets` 또는 환경변수로 등록하거나 아래에 직접 입력하세요.")
            service_key = st.text_input("SERVICE_KEY 직접 입력", type="password")
        else:
            st.success("SERVICE_KEY 로드 완료 (secrets/env)", icon="🔑")

        st.markdown("---")

        inqry_div_label = st.radio(
            "조회 기준 (inqryDiv)",
            options=["공고게시일 기준", "개찰일 기준"],
            index=0,
        )
        inqry_div = 1 if inqry_div_label.startswith("공고") else 2

        today = datetime.today().date()
        default_start = today.replace(day=1)

        start_date = st.date_input("조회 시작일", value=default_start)
        end_date   = st.date_input("조회 종료일", value=today)

        st.markdown("---")
        bid_name = st.text_input("공고명 검색어", placeholder="예: 실내건축, 증축, 보수공사 등")
        industry_name = st.text_input("업종명 검색어", placeholder="예: 실내건축공사업")

        region_code = st.text_input("참가제한 지역코드", placeholder="예: 41 (경기도)")

        st.markdown(REGION_CODE_HELP)

        st.markdown("---")
        col_price1, col_price2 = st.columns(2)
        with col_price1:
            min_price = st.text_input("최소 기초금액", placeholder="예: 100000000 또는 100,000,000")
        with col_price2:
            max_price = st.text_input("최대 기초금액", placeholder="예: 300000000 또는 300,000,000")

        st.markdown("---")
        contract_filter_label = st.radio(
            "계약방법 필터",
            options=["전체", "수의계약만", "수의계약 제외"],
            index=0,
        )
        if contract_filter_label == "전체":
            contract_filter = "all"
        elif contract_filter_label == "수의계약만":
            contract_filter = "only_private"
        else:
            contract_filter = "exclude_private"

        st.markdown("---")
        page_no = st.slider("페이지 (pageNo)", min_value=1, max_value=10, value=1, step=1)
        num_rows = st.slider("행 수 (numOfRows)", min_value=10, max_value=500, value=100, step=10)

        st.markdown("---")
        run_button = st.button("🔍 공고 검색 실행", use_container_width=True)

    # --- 메인 영역 ---
    if run_button:
        with st.spinner("나라장터에서 데이터를 불러오는 중입니다..."):
            log_text, df_result = search_bids(
                service_key=service_key,
                start_date=start_date,
                end_date=end_date,
                inqry_div=inqry_div,
                bid_name=bid_name,
                industry_name=industry_name,
                region_code=region_code,
                min_price=min_price,
                max_price=max_price,
                contract_filter=contract_filter,
                page_no=page_no,
                num_rows=num_rows,
            )

        # 로그 출력 (상단)
        with st.expander("📘 처리 로그 열기/닫기", expanded=True):
            st.text(log_text)

        if df_result.empty:
            st.warning("조건에 해당하는 공고가 없습니다.")
            return

        # 요약 메트릭
        st.subheader("📊 검색 요약")
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("조회된 공고 수", f"{len(df_result):,} 건")
        with col_m2:
            st.metric("조회 기준", inqry_div_label)
        with col_m3:
            st.metric("페이지 / 행 수", f"{page_no} / {num_rows}")

        st.markdown("---")

        # 결과 테이블
        st.subheader("📋 검색 결과 테이블")
        st.dataframe(df_result, use_container_width=True)

        # 엑셀 다운로드
        st.markdown("### 💾 엑셀 다운로드")
        buffer = None
        try:
            from io import BytesIO
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_result.to_excel(writer, index=False)
            buffer.seek(0)
        except Exception as e:
            st.error(f"엑셀 생성 중 오류: {e}")

        if buffer:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"나라장터_공사공고_{ts}.xlsx"
            st.download_button(
                label="엑셀 파일 다운로드",
                data=buffer,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    else:
        st.info("좌측 사이드바에서 조건을 설정한 후 **'🔍 공고 검색 실행'** 버튼을 눌러주세요.")


if __name__ == "__main__":
    main()

