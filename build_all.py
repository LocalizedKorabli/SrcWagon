"""
SrcWagon 多语言版批量生成器
从用户指定的 Source Han Sans 多语言字体目录，自动检测可用的语言变体，
分别与 ALS Wagon 合并，输出到各自文件夹。

用法: python build_all.py [Source Han Sans 目录路径]
"""

import os
import sys
import re
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
ALS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base", "ALS_Wagon")
CN_PROJECT_DIR = r"C:\Users\HoloI\Documents\dev\lesta\ships\mods\SrcWagon\SrcWagonCHS"
OUTPUT_BASE = os.path.join(WORKSPACE_DIR, "Releases")

# 目标语种与输出命名
# (输出标签, 主locale名, 备选locale名)
LOCALES = [
    ("CN", "SC", "CN"),
    ("TW", "TC", "TW"),
    ("HK", "HC", "HK"),
    ("JP", "JP", None),
]
LOCALE_DISPLAY = {
    "CN": "中国大陆 (Simplified Chinese)",
    "TW": "台湾省 (Traditional Chinese)",
    "HK": "香港 (Hong Kong)",
    "JP": "日本 (Japanese)",
}

# CJK 范围
CJK_RANGES = [
    range(0x4E00, 0x9FFF + 1), range(0x3400, 0x4DBF + 1),
    range(0xF900, 0xFAFF + 1), range(0x2E80, 0x2EFF + 1),
    range(0x2F00, 0x2FDF + 1), range(0x3000, 0x303F + 1),
    range(0x31C0, 0x31EF + 1), range(0x3200, 0x32FF + 1),
    range(0x3300, 0x33FF + 1), range(0xFF00, 0xFFEF + 1),
    range(0xFE10, 0xFE1F + 1), range(0xFE50, 0xFE6F + 1),
    range(0xFE30, 0xFE4F + 1),
]
HANGUL_RANGES = [
    range(0x1100, 0x11FF + 1), range(0xAC00, 0xD7AF + 1),
    range(0xA960, 0xA9FC + 1), range(0xD7B0, 0xD7FF + 1),
    range(0x3130, 0x318F + 1), range(0xFFA0, 0xFFDC + 1),
]
SCALE = 0.96


def is_cjk(cp):
    for r in CJK_RANGES:
        if cp in r:
            return True
    return False


def is_hangul(cp):
    for r in HANGUL_RANGES:
        if cp in r:
            return True
    return False


# ============================================================
# 字体发现
# ============================================================

def discover_fonts(font_dir):
    """扫描目录，发现所有 Source Han Sans VF 或静态字体文件"""
    font_dir = os.path.abspath(font_dir)
    print(f"扫描字体目录: {font_dir}")
    if not os.path.isdir(font_dir):
        print("  错误: 目录不存在")
        return {}

    # 所有可能的 locale 标识
    locale_ids = "SC|TC|HC|CN|TW|HK|JP|K|KR"
    pattern = re.compile(
        r'SourceHanSans'
        r'(?P<locale>' + locale_ids + r')?'
        r'(?:[-_])?'
        r'(?P<weight>Bold|Medium|Regular|Light|Heavy|ExtraLight|Normal)?'
        r'(?:[-_])?'
        r'(?P<vf>VF)?'
        r'\.(?P<ext>ttf|otf)$',
        re.IGNORECASE
    )

    # locale 归一化: 将 CN/TW/HK/KR 映射到 SC/TC/HC/K
    locale_norm = {"CN": "SC", "TW": "TC", "HK": "HC", "KR": "K"}

    found = {}
    for root, dirs, files in os.walk(font_dir):
        for fname in files:
            m = pattern.search(fname)
            if not m:
                continue
            raw_locale = (m.group('locale') or '').upper()
            locale = locale_norm.get(raw_locale, raw_locale)
            is_vf = m.group('vf') is not None
            weight = (m.group('weight') or '').lower()
            full_path = os.path.join(root, fname)

            if locale not in found:
                found[locale] = {"vf": None, "bold": None, "medium": None}
            if is_vf:
                found[locale]["vf"] = full_path
            elif weight == 'bold':
                found[locale]["bold"] = full_path
            elif weight == 'medium':
                found[locale]["medium"] = full_path
            elif weight == 'regular' and not found[locale]["medium"]:
                found[locale]["medium"] = full_path

    return found


# ============================================================
# 字形处理
# ============================================================

def extract_instance(vf_path, weight, output_path):
    print(f"    提取 wght={weight}...", end=" ", flush=True)
    from copy import deepcopy
    font = TTFont(vf_path)
    fs = deepcopy(font)
    instantiateVariableFont(fs, {"wght": weight}, inplace=True, updateFontNames=True)
    font.close()
    fs.save(output_path)
    fs.close()
    print(f"OK -> {os.path.basename(output_path)}")


def scale_glyph_inplace(glyf_table, glyph_name):
    g = glyf_table[glyph_name]
    if g is None or g.numberOfContours == 0:
        return
    if g.numberOfContours > 0:
        coords = g.coordinates
        for i in range(len(coords)):
            x, y = coords[i]
            coords[i] = (int(round(x * SCALE)), int(round(y * SCALE)))
        g.recalcBounds(glyf_table)
    elif g.numberOfContours == -1 and hasattr(g, 'components'):
        for comp in g.components:
            if hasattr(comp, 'x'): comp.x = int(round(comp.x * SCALE))
            if hasattr(comp, 'y'): comp.y = int(round(comp.y * SCALE))
            if hasattr(comp, 'transform') and comp.transform:
                a, b, c, d, e, f = comp.transform
                comp.transform = (a * SCALE, b, c, d * SCALE, e, f)
        g.recalcBounds(glyf_table)


def generate_one(output_tag, src_path, cn_path, weight_label):
    """生成一个语种+字重版本"""
    weight_wght = 700 if weight_label == "Bold" else 500

    print(f"\n  [{output_tag}] {weight_label}")
    print(f"    基底: {os.path.basename(cn_path)}")
    print(f"    来源: {os.path.basename(src_path)}")

    font = TTFont(cn_path)
    font_src = TTFont(src_path)

    cmap_base = font.getBestCmap()
    cmap_src = font_src.getBestCmap()
    glyf = font['glyf']
    glyf_src = font_src['glyf']
    hmtx = font['hmtx']
    hmtx_src = font_src['hmtx']
    glyph_order = list(font.getGlyphOrder())
    existing_names = set(glyph_order)
    cmap_tables = font['cmap'].tables

    # 阶段 1: 补充缺失字符
    added = 0
    skip_hangul = 0
    scaled_all = set()
    for cp in sorted(cmap_src.keys()):
        if cp in cmap_base:
            continue
        if is_hangul(cp):
            skip_hangul += 1
            continue
        gn = cmap_src[cp]
        if gn not in glyf_src:
            continue
        new_name = f"u{cp:05X}"
        if new_name in existing_names:
            continue
        if gn not in scaled_all:
            scale_glyph_inplace(glyf_src, gn)
            scaled_all.add(gn)
        glyf[new_name] = glyf_src[gn]
        if gn in hmtx_src.metrics:
            hmtx[new_name] = hmtx_src.metrics[gn]
        glyph_order.append(new_name)
        existing_names.add(new_name)
        for tbl in cmap_tables:
            if hasattr(tbl, 'cmap') and tbl.format in (4, 12):
                if tbl.format == 4 and cp > 0xFFFF:
                    continue
                tbl.cmap[cp] = new_name
        added += 1
    print(f"    补充: {added} (跳过谚文 {skip_hangul})")

    # 阶段 2: 替换 CJK

    replaced = 0
    for cp in sorted(cmap_base.keys()):
        if not is_cjk(cp):
            continue
        if cp not in cmap_src:
            continue
        gn_src = cmap_src[cp]
        if gn_src not in glyf_src:
            continue
        gn_base = cmap_base[cp]
        if gn_src not in scaled_all:
            scale_glyph_inplace(glyf_src, gn_src)
            scaled_all.add(gn_src)
        glyf[gn_base] = glyf_src[gn_src]
        replaced += 1
    print(f"    替换 CJK: {replaced}")

    # 更新表格
    font['maxp'].numGlyphs = len(glyph_order)
    font.setGlyphOrder(glyph_order)
    font['OS/2'].usWeightClass = weight_wght

    bmp_cps = [cp for cp in cmap_base.keys() if cp <= 0xFFFF]
    for tbl in cmap_tables:
        if hasattr(tbl, 'cmap') and tbl.format in (4, 12):
            bmp_cps.extend([cp for cp in tbl.cmap.keys() if cp <= 0xFFFF])
    if bmp_cps:
        font['OS/2'].usFirstCharIndex = min(bmp_cps)
        font['OS/2'].usLastCharIndex = max(bmp_cps)

    # 名称表
    font_name = f"SrcWagon {output_tag}"
    for rec in font['name'].names:
        if rec.platformID == 3 and rec.langID == 0x409:
            if rec.nameID in (1, 16):
                rec.string = font_name
            elif rec.nameID == 4:
                rec.string = f"{font_name} {weight_label}"
            elif rec.nameID == 6:
                rec.string = f"SrcWagon{output_tag}-{weight_label}"
            elif rec.nameID in (2, 17):
                rec.string = weight_label
            elif rec.nameID == 10:
                rec.string = f"ALS Wagon + Source Han Sans {output_tag}."

    # 保存
    out_dir = os.path.join(OUTPUT_BASE, f"SrcWagon-{output_tag}", "fonts")
    os.makedirs(out_dir, exist_ok=True)
    out_name = f"SourceHanSans{output_tag}_WN_{weight_label}.ttf"
    out_path = os.path.join(out_dir, out_name)
    font.save(out_path)
    font.close()
    font_src.close()
    print(f"    保存: {out_name} ({len(glyph_order)} 字形)")
    return out_path


def build_locale(output_tag, locale_key, locale_info):
    """为一个语种构建两个字重（Medium + Bold）"""
    locale_name = LOCALE_DISPLAY.get(output_tag, output_tag)
    print(f"\n{'#'*65}")
    print(f"#  {locale_name} ({output_tag})")
    print(f"{'#'*65}")

    results = []
    for weight, wlabel in [(500, "Medium"), (700, "Bold")]:
        # 确定源字体
        src_path = None
        temp_path = None
        if locale_info["vf"]:
            temp_path = os.path.join(WORKSPACE_DIR, f"temp_{locale_key}_{wlabel}.ttf")
            extract_instance(locale_info["vf"], weight, temp_path)
            src_path = temp_path
        elif wlabel == "Bold" and locale_info["bold"]:
            src_path = locale_info["bold"]
        elif wlabel == "Medium" and locale_info["medium"]:
            src_path = locale_info["medium"]
        else:
            print(f"  跳过 {wlabel}: 无可用字体")
            continue

        # CN 基底
        cn_path = os.path.join(CN_PROJECT_DIR, "SrcWagon", "Common", "res_mods", "gui", "fonts",
                                f"SourceHanSansCN_WN_{wlabel}.ttf")
        if not os.path.exists(cn_path):
            print(f"  错误: CN 基底缺失: {cn_path}")
            continue

        result = generate_one(output_tag, src_path, cn_path, wlabel)
        if result:
            results.append(result)

        # 清理临时 VF 提取文件
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    return results


def main():
    print("=" * 70)
    print("  SrcWagon 多语言版批量生成器")
    print("  ALS Wagon + Source Han Sans 多语言变体")
    print("=" * 70)

    # 字体目录
    font_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "base", "SourceHanSans")

    # 扫描
    found = discover_fonts(font_dir)
    if not found:
        print("未找到 Source Han Sans 字体。")
        sys.exit(1)

    print(f"\n已发现语种: {', '.join(sorted(found.keys()))}")
    for k, v in sorted(found.items()):
        src = os.path.basename(v["vf"]) if v["vf"] else \
              os.path.basename(v["bold"] or v["medium"] or "?")
        print(f"  {k}: {src}")

    # 确定哪些语种可以生成
    to_build = []
    for tag, primary, alt in LOCALES:
        if primary in found:
            to_build.append((tag, primary, found[primary]))
        elif alt and alt in found:
            to_build.append((tag, alt, found[alt]))
        else:
            # 如果主/备都没有，看看有没有 Pan-CJK VF
            if "Pan" in found:
                print(f"\n  [{tag}] 未找到专用字体，将使用 Pan-CJK VF")
                to_build.append((tag, "Pan", found["Pan"]))

    if not to_build:
        print("没有可用的语种。")
        sys.exit(1)

    print(f"\n将生成: {', '.join(t for t, _, _ in to_build)}")

    # 逐语种构建
    total = 0
    for tag, key, info in to_build:
        results = build_locale(tag, key, info)
        total += len(results)

    print(f"\n{'='*70}")
    print(f"  完成！共生成 {total} 个字体文件")
    for tag, _, _ in to_build:
        d = os.path.join(OUTPUT_BASE, f"SrcWagon-{tag}")
        n = LOCALE_DISPLAY.get(tag, tag)
        print(f"    {n:>10} -> {d}")
        print(f"    {d}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
