from __future__ import annotations

import re

PROCESS_NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^毛坯准备$"), "备料"),
    (re.compile(r"^备料(准备)?$"), "备料"),
    (re.compile(r"^按图下料.*$"), "下料"),
    (re.compile(r"^下料[Φ⌀].*$"), "下料"),
    (re.compile(r"^(外观)?检验$"), "检验"),
    (re.compile(r"^外观检验$"), "外观检查"),
    (re.compile(r"^尺寸检验$"), "检验"),
    (re.compile(r"^磁粉检验$"), "磁粉检查"),
    (re.compile(r"^烧伤检验$"), "烧伤检查"),
    (re.compile(r"^裂纹检验$"), "裂纹检查"),
    (re.compile(r"^荧光检验$"), "荧光检查"),
    (re.compile(r"^真空淬火(处理)?$"), "真空淬火"),
    (re.compile(r"^调质(处理)?$"), "调质"),
    (re.compile(r"^去应力(处理|退火)?$"), "去应力"),
    (re.compile(r"^镀铜(处理)?$"), "镀铜"),
    (re.compile(r"^(渗氮|滲氮)(处理)?$"), "渗氮"),
    (re.compile(r"^氰化(处理)?$"), "氰化"),
    (re.compile(r"^除铜(处理)?$"), "除铜"),
    (re.compile(r"^铬酸阳极化(处理)?$"), "铬酸阳极化"),
    (re.compile(r"^硬质阳极化(处理)?$"), "硬质阳极化"),
    (re.compile(r"^钝化(处理)?$"), "钝化"),
    (re.compile(r"^清洗(处理)?$"), "清洗"),
    (re.compile(r"^多功能清洗$"), "清洗"),
    (re.compile(r"^去毛刺(处理)?$"), "去毛刺"),
    (re.compile(r"^标记$"), "标印"),
    (re.compile(r"^标引$"), "标印"),
    (re.compile(r"^打标$"), "标印"),
    (re.compile(r"^钻[、,/／]?铰孔$"), "钻铰孔"),
    (re.compile(r"^钻铰(孔)?$"), "钻铰孔"),
    (re.compile(r"^钻[、,/／]?镗孔$"), "钻镗孔"),
    (re.compile(r"^钻镗孔.*$"), "钻镗孔"),
    (re.compile(r"^钻铰孔.*$"), "钻铰孔"),
    (re.compile(r"^攻螺纹.*$"), "攻螺纹"),
    (re.compile(r"^倒角[、,，/]?倒圆$"), "倒角"),
    (re.compile(r"^孔口倒角$"), "孔口倒角"),
    (re.compile(r"^磨外$"), "磨外圆"),
    (re.compile(r"^.*内圆磨.*$"), "磨孔"),
    (re.compile(r"^(数控)?外圆磨.*$"), "磨外圆"),
    (re.compile(r"^(数控)?无心磨.*$"), "磨外圆"),
    (re.compile(r"^.*外圆磨.*$"), "磨外圆"),
    (re.compile(r"^磨孔(加工)?$"), "磨孔"),
]

TURNING_SIDE_LABEL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("车削加工（第1次）", "车削加工（A侧）"),
    ("车削加工（第2次）", "车削加工（B侧）"),
)

_FACTOR_LABELS: dict[str, str] = {
    "always=true": "属于常规主线工序",
    "has_hole=true": "存在内孔 / 通孔 / 中心孔",
    "has_spline=true": "存在槽 / 键 / 花键结构",
    "hardness=HIGH": "高硬度或强化热处理要求",
    "material!=空": "材料牌号会影响该工序",
    "roughness<=0.8": "高精度 / 高表面质量要求",
    "has_final=true": "需要终热处理",
    "has_vac=true": "需要真空淬火",
    "hole_complex=true": "孔系较复杂",
    "has_milling=true": "存在槽 / 扁 / 铣削特征",
    "has_relief=true": "需要去应力",
    "need_trace=true": "需要追溯标印",
    "need_mt=true": "需要磁粉检查",
    "need_burn_check=true": "需要烧伤检查",
    "structure_type=活门类": "属于活门类结构",
    "structure_type=衬套类": "属于衬套类结构",
    "外圆结构要求": "存在外圆主形面或回转外形需求",
    "台阶外形要求": "存在台阶外圆或轴肩轮廓需求",
    "外圆基准要求": "外圆承担定位或检测基准作用",
    "外圆配合要求": "外圆属于关键配合面或定尺寸面",
    "回转轮廓要求": "存在锥面、圆弧或过渡回转轮廓",
    "外形轮廓要求": "存在需要车削成形的局部外形轮廓",
    "端面基准要求": "端面承担基准或定位作用",
    "端面贴合要求": "存在贴合端面或台阶端面要求",
    "孔口端面要求": "存在孔口端面或沉台结构要求",
    "端面配合要求": "端面与外圆或内孔存在配合关系",
    "锐边去除要求": "需要处理锐边、毛刺或边缘过渡",
    "孔口倒角要求": "孔口需要导入或倒角处理",
    "装配导入要求": "需要装配导入或防划伤处理",
    "孔结构类型": "存在通孔、盲孔或一般孔结构需求",
    "中心孔定位要求": "存在中心孔或定位孔需求",
    "孔复合要求": "存在阶梯孔、孔台阶或复合孔需求",
    "深长孔要求": "存在深孔或长孔结构需求",
    "孔可达性限制": "孔位可达性、排屑或加工空间受限",
    "孔尺寸精度要求": "孔径尺寸精度要求较高",
    "孔形位精度要求": "孔圆度、圆柱度或位置精度要求较高",
    "孔表面质量要求": "孔表面粗糙度或光整要求较高",
    "孔配合要求": "孔属于关键配合孔或定尺寸孔",
    "配对加工要求": "需要与配对件联动定尺寸",
    "分组配套要求": "需要分组配套或按实测尺寸配合",
    "尺寸公差高": "尺寸公差要求较高",
    "形位精度要求": "圆度、圆柱度、跳动或位置精度要求较高",
    "最终光整要求": "需要最终光整，而不只是一般磨削",
    "装配配合要求": "属于关键装配面、贴合面或密封面",
    "热处理链分化": "材料或技术条件会改变热处理链",
    "热后精整要求": "热处理后仍需补充精整或定尺寸",
    "性能与耐磨要求": "耐磨、寿命或性能指标驱动该工序",
    "尺寸稳定性要求": "长期尺寸稳定性要求较高",
    "被相邻工序一并完成": "常与相邻主工序一并完成",
    "作为上位工序局部内容": "通常属于上位工序中的局部动作",
    "局部特征单列": "只在局部结构或特殊样本中单独列出",
    "命名未统一": "原始文件里存在不同叫法或别名混用",
    "记录口径差异": "文档记录方式或写法不同",
    "文档记录差异": "文档省略、合并记录或抽取口径不同",
    "热处理尺寸边界": "截面尺寸或有效热处理深度影响工序安排",
    "热处理结构风险": "结构形状或变形风险影响热处理工序选择",
}


def clean_process_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").strip()


def normalize_process_name(name: str) -> str:
    cleaned = clean_process_text(name)
    cleaned = cleaned.strip("：:;；，,。./")
    cleaned = cleaned.replace("／", "/")
    if cleaned in {"钻、铰孔", "钻/铰孔", "钻，铰孔", "钻／铰孔"}:
        cleaned = re.sub(r"[、,，/]+", "", cleaned)
    for pattern, normalized in PROCESS_NORMALIZATION_RULES:
        if pattern.fullmatch(cleaned):
            return normalized
    return cleaned


def canonicalize_route_label(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    for source_label, target_label in TURNING_SIDE_LABEL_REPLACEMENTS:
        normalized = normalized.replace(source_label, target_label)
    if normalized == "标印":
        normalized = "标记"
    normalized = normalized.replace("标印（", "标记（")
    return normalized


def canonical_route_operation_name(name: str) -> str:
    return canonicalize_route_label(normalize_process_name(name or ""))


def infer_operation_family(name: str) -> str:
    normalized = normalize_process_name(name or "")
    if not normalized:
        return "generic"
    if normalized in {"备料", "下料", "毛坯准备/下料"}:
        return "prep"
    if any(token in normalized for token in ("端面", "平端面")):
        return "end_face"
    if any(token in normalized for token in ("倒角", "倒圆", "孔口倒角", "锐边")):
        return "chamfer"
    if any(token in normalized for token in ("磁粉检查", "烧伤检查", "裂纹检查", "荧光检查", "检验", "检查", "探伤")):
        return "inspection"
    if any(token in normalized for token in ("调质", "正常化", "去应力", "淬火", "真空淬火", "热处理", "镀铜", "渗氮", "氰化", "除铜", "钝化", "阳极化", "时效")):
        return "heat"
    if any(token in normalized for token in ("磨外圆", "研外圆", "磨端面", "磨槽", "精磨", "镜面磨")):
        return "finish"
    if any(token in normalized for token in ("磨孔", "研孔", "珩孔")):
        return "hole_finish"
    if any(token in normalized for token in ("孔", "钻", "镗", "铰", "攻螺纹", "攻丝", "内圆")):
        return "hole"
    if any(token in normalized for token in ("铣槽", "铣扁", "车槽", "割型孔", "割扁", "花键", "键槽", "槽")):
        return "feature"
    if any(token in normalized for token in ("车零件", "车外形", "车外圆", "精车外圆", "粗车外圆", "外圆")):
        return "outer_surface"
    if any(token in normalized for token in ("去毛刺", "清洗", "标印", "包装")):
        return "release"
    return "generic"


def infer_merge_family_key(name: str) -> str:
    family = infer_operation_family(name)
    if family in {"prep", "outer_surface", "end_face"}:
        return "shape"
    if family in {"hole", "hole_finish"}:
        return "hole"
    if family == "feature":
        return "feature"
    if family == "heat":
        return "heat"
    if family == "inspection":
        return "inspection"
    if family in {"release", "chamfer"}:
        return "release"
    return normalize_process_name(name or "") or "other"


def factor_display_label(factor_name: str) -> str:
    factor = (factor_name or "").strip()
    if factor in _FACTOR_LABELS:
        return _FACTOR_LABELS[factor]
    if factor.startswith("material="):
        return f"材料为 {factor.split('=', 1)[1]}"
    return factor


def is_likely_mainline_operation(name: str) -> bool:
    family = infer_operation_family(name)
    return family in {
        "prep",
        "outer_surface",
        "end_face",
        "hole",
        "feature",
        "chamfer",
        "release",
        "inspection",
    }
