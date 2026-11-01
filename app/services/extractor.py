"""元数据抽取（ING-005）：文号、发文机关、日期、效力位阶、主题、适用主体、地域、时效。

效力位阶判定为**代码硬约束**（项目书 10.5），不由模型自由判断；
每份文档输出判定依据 level_reason，供人工复核。
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Dict, List

from app.core.constants import (
    APPLICABLE_SUBJECTS,
    CITY_PROVINCE,
    EFFECT_LEVEL_RANK,
    LEVEL_PATTERNS,
    PROVINCES,
    SUBJECT_KEYWORDS,
    TOPICS,
    TOPIC_KEYWORDS,
)
from app.services.text_utils import extract_dates, normalize_date

RE_DOC_NUMBER = re.compile(
    r"[\u4e00-\u9fa5A-Za-z]{0,12}[〔\[（(]\s*(19|20)\d{2}\s*[〕\]）)]?\s*第?\s*\d{1,5}\s*号"
)
RE_DOC_NUMBER_SIMPLE = re.compile(r"[(（〔\[]\s*(19|20)\d{2}\s*[)）〕\]]\s*第?\s*\d{1,5}\s*号")
RE_LAW_REF = re.compile(r"《([^》]{2,40})》")
RE_AUTHORITY = re.compile(
    r"([\u4e00-\u9fa5]{2,20}(?:国务院|人民政府|人民代表大会常务委员会|部|委员会|厅|局|署|办|委))"
)
RE_TITLE_LINE = re.compile(r"^\s*(.{6,80}(?:法|条例|规定|办法|意见|通知|方案|细则|决定|公告|指引|指南))\s*$")
# 结构化元信息头（样本/清洗后的文本可能带“发文机关：”等行）
RE_META_AUTHORITY = re.compile(r"^\s*发文机关[：:]\s*(.+?)\s*$", re.M)
RE_META_DOC_NUMBER = re.compile(r"^\s*文号[：:]\s*(.+?)\s*$", re.M)
RE_META_PUBLISH = re.compile(
    r"^\s*(?:印发|发布|公布)?日期[：:]?\s*((?:19|20)\d{2}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)", re.M
)
# 发文机关中的行政区划名（省 / 市 / 县 / 区）
RE_AUTH_REGION = re.compile(r"^([\u4e00-\u9fa5]{2,10}(?:省|市|县|区|自治区))")

# 主送机关 / 抬头产生的噪音，不应作为发文机关
NOISE_AUTHORITY_PREFIX = ("各县", "各区", "各市", "各镇", "各乡", "各有关", "各直属", "经", "市委", "市政府各")

NATIONAL_HINT = ["国务院", "全国人民代表大会", "常务委员会", "财政部", "发改委", "工业和信息化部",
                 "科学技术部", "税务总局", "市场监管总局", "国家"]
PROVINCE_HINT = ["省人民政府", "省人大常委会", "自治区", "省"]
CITY_HINT = ["市人民政府", "市人大常委会", "市"]
DISTRICT_HINT = ["区人民政府", "县人民政府"]


def extract_title(text: str, filename: str = "") -> str:
    for line in text.splitlines()[:15]:
        line = line.strip()
        if not line:
            continue
        if RE_TITLE_LINE.match(line) and len(line) <= 80:
            return line
        if line.startswith("关于印发") or line.startswith("关于"):
            return line[:80]
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    if first and len(first) <= 80:
        return first
    return filename or "未命名政策文件"


def extract_document_number(text: str) -> str:
    """抽取文号。

    结构化元信息头「文号：」优先且权威——避免误取正文里引用的上位法文号
    （如某市工作方案正文出现「工信厅联规函〔2026〕169号」）。
    - 元信息头存在且含标准文号（带年份括号 + 号）→ 直接采用；
    - 元信息头存在但明确「未标注 / 无文号」等 → 视为无文号，不回退扫描正文；
    - 元信息头缺失 → 回退扫描全文。
    """
    m = RE_META_DOC_NUMBER.search(text[:2000])
    if m:
        val = (m.group(1) or "").strip()
        cand = RE_DOC_NUMBER.search(val) or RE_DOC_NUMBER_SIMPLE.search(val)
        if cand:
            return cand.group(0).strip()
        return ""  # 头存在但无有效文号：信任结构化标注，不扫描正文
    m = RE_DOC_NUMBER.search(text) or RE_DOC_NUMBER_SIMPLE.search(text)
    return m.group(0).strip() if m else ""


def _is_noise_authority(name: str) -> bool:
    return name.startswith(NOISE_AUTHORITY_PREFIX) or "管委会" in name or len(name) < 4


def extract_authorities(text: str) -> List[str]:
    """抽取发文机关。

    优先级：①结构化元信息行“发文机关：” ②正文抬头中的机关名。
    主送机关（各县市区人民政府…）、开发区管委会等会被剔除，避免污染位阶与层级判定。
    """
    m = RE_META_AUTHORITY.search(text[:2000])
    if m:
        raw = [x.strip() for x in re.split(r"[、,，/]|(?<=局)\s|(?<=委员会)\s", m.group(1)) if x.strip()]
        found = [x for x in raw if not _is_noise_authority(x)]
        if found:
            return found[:5]

    head = "\n".join(text.splitlines()[:20])
    found = []
    for m in RE_AUTHORITY.finditer(head):
        name = m.group(1).strip()
        if name in found or _is_noise_authority(name):
            continue
        found.append(name)
    if not found:
        for line in head.splitlines():
            if line.endswith(("：", ":")) and 2 <= len(line) <= 20:
                found.append(line.rstrip("：:"))
                break
    return found[:5]


def detect_effect_level(title: str, text: str, authorities: List[str]) -> Dict[str, str]:
    """位阶硬判定，返回 {code, name, rank, reason}。

    判定依据**只取标题与发文机关**，不扫描正文——正文引用上位法（如“根据《国务院办公厅…》”）
    不得改变文件自身的效力位阶，否则会把手规范性文件误判为行政法规。
    """
    authority_text = " ".join(authorities)
    scope = f"{title} {authority_text}".strip()

    def hit(keyword: str) -> bool:
        return keyword in scope

    if hit("宪法"):
        return {"code": "CONSTITUTION", "name": "宪法", "reason": "命中关键词：宪法"}
    if hit("全国人民代表大会常务委员会") and title.strip().endswith("法"):
        return {"code": "LAW", "name": "法律", "reason": "全国人大常委会通过且名称为“法”"}
    if hit("国务院令") or (hit("国务院") and re.search(r"(条例|办法|规定)$", title.strip())):
        return {"code": "ADMIN_REG", "name": "行政法规", "reason": "国务院制定/国务院令"}
    if re.search(r"[省市区县]\s*人民代表大会常务委员会", scope) or hit("地方性法规"):
        return {"code": "LOCAL_REG", "name": "地方性法规", "reason": "地方人大常委会制定"}
    if re.search(r"(部令|委员会令|局令|署令|部门规章)", scope):
        return {"code": "DEPT_RULE", "name": "部门规章", "reason": "国务院部门令/部门规章"}
    if re.search(r"[省市区县]\s*人民政府令", scope):
        return {"code": "LOCAL_RULE", "name": "地方政府规章", "reason": "地方政府令"}
    # 兜底一：标题后缀命中规范性文件关键词
    for keyword in LEVEL_PATTERNS[-1][1]:
        if title.strip().endswith(keyword):
            return {
                "code": "NORMATIVE",
                "name": "规范性文件",
                "reason": f"标题以“{keyword}”结尾，且发文机关为行政机关",
            }
    # 兜底二：发文机关为行政机关但标题未命中（如“若干举措”“行动方案（2025-2027年）”）
    if re.search(r"(人民政府|人民代表大会|委员会|管理局|办公室|厅|局)", authority_text):
        return {
            "code": "NORMATIVE",
            "name": "规范性文件",
            "reason": "发文机关为行政机关且无上位位阶特征，按规范性文件归类",
        }
    return {"code": "OTHER", "name": "其他", "reason": "未命中任何位阶规则，需人工复核"}


def detect_institution_level(authorities: List[str], text: str = "") -> str:
    """按**发文机关**判定机构层级，避免被抬头中的“各县市区人民政府”带偏。"""
    joined = " ".join(authorities)
    if not joined.strip():
        joined = "\n".join(text.splitlines()[:10])
    if re.search(r"(?:区|县)人民政府", joined):
        return "DISTRICT"
    if re.search(r"市人民政府|[\u4e00-\u9fa5]{2,6}市(?!场|民|区)", joined):
        return "CITY"
    if re.search(r"(?:省|自治区)人民政府|(?:省|自治区)人民代表大会", joined):
        return "PROVINCE"
    if any(h in joined for h in NATIONAL_HINT):
        return "NATIONAL"
    return "OTHER"


def detect_topics(text: str, limit: int = 3) -> List[str]:
    scores = {topic: 0 for topic in TOPICS}
    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            scores[topic] += text.count(keyword)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [topic for topic, score in ranked if score > 0][:limit] or ["其他"]


def detect_subjects(text: str) -> List[str]:
    found = []
    for subject, keywords in SUBJECT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            found.append(subject)
    return found or ["其他"]


def detect_jurisdiction(text: str, authorities: List[str] = None) -> List[str]:
    """适用地域：发文机关中的行政区划 + 正文中出现的省份名。"""
    found: List[str] = []
    for name in authorities or []:
        m = RE_AUTH_REGION.match(name.strip())
        if not m:
            continue
        region = m.group(1)
        province = CITY_PROVINCE.get(region)
        if province and province not in found:
            found.append(province)
        if region not in found:
            found.append(region)
    for p in PROVINCES:
        if p in text and p not in found:
            found.append(p)
    if not found:
        return ["全国"]
    return found[:5]


def detect_validity(text: str, publish_date: str, effective_date: str, expiry_date: str) -> Dict[str, str]:
    today = dt.date.today()
    if re.search(r"(废止|停止执行|不再执行|失效)", text[:2000]):
        return {"status": "ABOLISHED", "reason": "文本中出现“废止/失效”表述"}
    if expiry_date:
        try:
            if dt.date.fromisoformat(expiry_date) < today:
                return {"status": "EXPIRED", "reason": f"有效期至 {expiry_date}，已过期"}
        except ValueError:
            pass
    if effective_date:
        try:
            if dt.date.fromisoformat(effective_date) > today:
                return {"status": "FUTURE", "reason": f"生效日期 {effective_date} 晚于今日"}
        except ValueError:
            pass
    if re.search(r"(自发布之日起施行|自印发之日起施行|现行有效)", text):
        return {"status": "EFFECTIVE", "reason": "含“自发布之日起施行”表述"}
    return {"status": "EFFECTIVE", "reason": "默认现行有效，待复核"}


CN_YEARS = {"两": 2, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _add_years(iso_date: str, years: int) -> str:
    try:
        d = dt.date.fromisoformat(iso_date)
    except ValueError:
        return ""
    try:
        return d.replace(year=d.year + years).isoformat()
    except ValueError:  # 2 月 29 日
        return d.replace(year=d.year + years, day=28).isoformat()


def extract_dates_from_text(text: str) -> Dict[str, str]:
    publish, effective, expiry = "", "", ""
    # 印发 / 发布日期（支持“印发日期：2025年3月20日”结构化写法）
    m = (RE_META_PUBLISH.search(text[:2000])
         or re.search(r"(印发|发布|公布|出台)(?:日期)?[：:]?\s*((?:19|20)\d{2}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)", text))
    if m:
        publish = normalize_date(m.group(1) if RE_META_PUBLISH.search(text[:2000]) else m.group(2))
    m = re.search(r"自\s*((?:19|20)\d{2}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)\s*(?:起)?(?:施行|执行|实施)", text)
    if m:
        effective = normalize_date(m.group(1))
    # 有效期：明确日期优先
    m = re.search(
        r"(?:有效期(?:至|截至|截止)?|有效期限至)[：:]?\s*((?:19|20)\d{2}[年\-/]\d{1,2}[月\-/]\d{1,2}日?)", text)
    if m:
        expiry = normalize_date(m.group(1))
    # 有效期：仅有年限（如“有效期两年”）时按印发日期推算
    if not expiry:
        m = re.search(r"有效期(?:为)?\s*([一两二三四五六七八九十\d]+)\s*年", text)
        if m and publish:
            raw = m.group(1)
            years = int(raw) if raw.isdigit() else CN_YEARS.get(raw, 0)
            if years:
                expiry = _add_years(publish, years)
    dates = extract_dates(text)
    if not publish and dates:
        publish = normalize_date(dates[0])
    if not effective and len(dates) > 1:
        effective = normalize_date(dates[1])
    return {"publish_date": publish, "effective_date": effective, "expiry_date": expiry}


def extract_higher_law_refs(text: str) -> List[str]:
    refs = []
    for m in RE_LAW_REF.finditer(text):
        name = m.group(1).strip()
        if name and name not in refs:
            refs.append(name)
    return refs[:10]


def extract_meta(text: str, filename: str = "") -> Dict:
    """汇总文档级元数据。"""
    title = extract_title(text, filename)
    authorities = extract_authorities(text)
    dates = extract_dates_from_text(text)
    level = detect_effect_level(title, text, authorities)
    validity = detect_validity(text, dates["publish_date"], dates["effective_date"], dates["expiry_date"])
    return {
        "title": title,
        "document_number": extract_document_number(text),
        "issuing_authority": authorities,
        "effect_level": level["code"],
        "effect_level_name": level["name"],
        "level_reason": level["reason"],
        "hierarchy_rank": EFFECT_LEVEL_RANK.get(level["code"], 10),
        "institution_level": detect_institution_level(authorities, text),
        "topics": detect_topics(text),
        "applicable_subjects": detect_subjects(text),
        "jurisdiction": detect_jurisdiction(text, authorities),
        "validity_status": validity["status"],
        "validity_reason": validity["reason"],
        "higher_law_refs": extract_higher_law_refs(text),
        **dates,
    }
