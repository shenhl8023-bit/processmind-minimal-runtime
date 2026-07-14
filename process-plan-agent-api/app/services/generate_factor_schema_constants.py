"""工艺路线生成因素 schema 的共享常量。"""

from __future__ import annotations

GROUP_ORDER = {
    "基础与材料": 10,
    "结构补充": 20,
    "热处理与性能": 30,
    "专项检查与放行": 40,
    "结构特征": 50,
    "精度与表面": 60,
    "其他因素": 90,
}

FIELD_LABELS = {
    "family": "零件家族",
    "material": "材料",
    "structure_type": "结构类型",
    "hardness": "交货硬度要求",
    "roughness": "表面粗糙度最高等级",
    "has_hole": "是否有内孔 / 中心孔",
    "has_spline": "是否有花键 / 键槽",
    "has_final": "是否需要终热处理",
    "has_vac": "是否采用真空淬火",
    "hole_complex": "孔系是否复杂",
    "has_milling": "是否有槽 / 扁特征",
    "has_relief": "是否需要去应力",
    "need_trace": "是否需要追溯标印",
    "need_mt": "是否需要磁粉检查",
    "need_burn_check": "是否需要烧伤检查",
}

BOOLEAN_FIELD_LABELS = {
    "has_hole": ("实心结构", "需要打孔"),
    "has_spline": ("无", "有"),
    "has_final": ("否", "是"),
    "has_vac": ("否", "是"),
    "hole_complex": ("否", "是"),
    "has_milling": ("否", "是"),
    "has_relief": ("否", "是"),
    "need_trace": ("否", "是"),
    "need_mt": ("否", "是"),
    "need_burn_check": ("否", "是"),
}

STANDARD_FACTOR_BLUEPRINT = [
    {
        "key": "material",
        "label": "材料",
        "group": "基础与材料",
        "input_type": "select",
        "required": True,
        "placeholder": None,
        "options": [
            ("9Cr18", "9Cr18"),
            ("6061", "6061"),
            ("4Cr14Ni14W2Mo", "4Cr14Ni14W2Mo"),
        ],
    },
    {
        "key": "structure_type",
        "label": "结构类型",
        "group": "基础与材料",
        "input_type": "select",
        "required": True,
        "placeholder": None,
        "options": [
            ("活门类", "活门类"),
            ("衬套类", "衬套类"),
        ],
    },
    {
        "key": "has_final",
        "label": "是否需要终热处理",
        "group": "热处理与性能",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
    {
        "key": "has_vac",
        "label": "是否采用真空淬火",
        "group": "热处理与性能",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
    {
        "key": "hole_complex",
        "label": "孔系是否复杂",
        "group": "结构补充",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
    {
        "key": "has_milling",
        "label": "是否有槽/扁特征",
        "group": "结构补充",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
    {
        "key": "has_relief",
        "label": "是否需要去应力",
        "group": "热处理与性能",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
    {
        "key": "need_trace",
        "label": "是否需要追溯标印",
        "group": "专项检查与放行",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
    {
        "key": "need_mt",
        "label": "是否需要磁粉检查",
        "group": "专项检查与放行",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
    {
        "key": "need_burn_check",
        "label": "是否需要烧伤检查",
        "group": "专项检查与放行",
        "input_type": "boolean",
        "required": False,
        "placeholder": None,
        "options": [("false", "否"), ("true", "是")],
    },
]


__all__ = [
    "BOOLEAN_FIELD_LABELS",
    "FIELD_LABELS",
    "GROUP_ORDER",
    "STANDARD_FACTOR_BLUEPRINT",
]
