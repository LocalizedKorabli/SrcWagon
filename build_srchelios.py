"""
SrcHelios-CN 字体生成器 (v2)
WarHelios (2048 upem) + Source Han Sans CN (1000 upem)
流程：
  1. 以 WarHelios 为基底（自带所有子字形）
  2. Source Han Sans CN 缩放所有坐标到 2048 upem
  3. CJK 字形从 CN 替换到 WarHelios
"""

import os
import sys
import copy
from fontTools.ttLib import TTFont

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(WORKSPACE_DIR, "base")
CN_FONTS_DIR = r"C:\Users\HoloI\Documents\dev\lesta\ships\mods\SrcWagon\SrcWagonCHS\SrcWagon\Common\res_mods\gui\fonts"
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "SrcHelios-CN", "gui", "fonts")

SCALE = 2048 / 1000  # 2.048

CJK_RANGES = [
    range(0x4E00, 0x9FFF + 1), range(0x3400, 0x4DBF + 1),
    range(0xF900, 0xFAFF + 1), range(0x2E80, 0x2EFF + 1),
    range(0x2F00, 0x2FDF + 1), range(0x3000, 0x303F + 1),
    range(0x31C0, 0x31EF + 1), range(0x3200, 0x32FF + 1),
    range(0x3300, 0x33FF + 1), range(0xFF00, 0xFFEF + 1),
    range(0xFE10, 0xFE1F + 1), range(0xFE50, 0xFE6F + 1),
    range(0xFE30, 0xFE4F + 1),
]

VARIANTS = [
    ("Medium", "Warhelios_Regular.ttf", "SourceHanSansCN_WN_Medium.ttf", 400),
    ("Bold", "Warhelios_Bold.ttf", "SourceHanSansCN_WN_Bold.ttf", 700),
]


def is_cjk(cp):
    for r in CJK_RANGES:
        if cp in r:
            return True
    return False


def scale_cn_glyphs(font, factor):
    """缩放 CN 字体中所有字形到 2048 upem"""
    glyf = font['glyf']
    for gn in list(font.getGlyphOrder()):
        g = glyf[gn]
        if g is None or g.numberOfContours == 0:
            continue
        if g.numberOfContours > 0:
            coords = g.coordinates
            for i in range(len(coords)):
                x, y = coords[i]
                coords[i] = (int(round(x * factor)), int(round(y * factor)))
            g.recalcBounds(glyf)
        elif g.numberOfContours == -1 and hasattr(g, 'components'):
            for comp in g.components:
                if hasattr(comp, 'x'): comp.x = int(round(comp.x * factor))
                if hasattr(comp, 'y'): comp.y = int(round(comp.y * factor))
                if hasattr(comp, 'transform') and comp.transform:
                    a, b, c, d, e, f = comp.transform
                    comp.transform = (a * factor, b, c, d * factor, e, f)
            g.recalcBounds(glyf)

    hmtx = font['hmtx']
    for gn in list(font.getGlyphOrder()):
        if gn in hmtx.metrics:
            w, lsb = hmtx.metrics[gn]
            hmtx.metrics[gn] = (int(round(w * factor)), int(round(lsb * factor)))


def build_srchelios(weight_label, war_name, cn_name, target_weight):
    print(f"\n{'='*60}")
    print(f"生成: {weight_label}")
    print('='*60)

    # 1. 以 WarHelios 为基底
    war_path = os.path.join(BASE_DIR, "WarHelios", war_name)
    font = TTFont(war_path)
    cmap_base = font.getBestCmap()
    print(f"  基底: {war_name}")
    print(f"    upem={font['head'].unitsPerEm}, glyphs={len(font.getGlyphOrder())}")

    # 2. 加载 Source Han Sans CN
    cn_path = os.path.join(CN_FONTS_DIR, cn_name)
    font_cn = TTFont(cn_path)
    cmap_cn = font_cn.getBestCmap()
    print(f"  来源: {cn_name}")
    print(f"    upem={font_cn['head'].unitsPerEm}, CJK={sum(1 for cp in cmap_cn if 0x4E00<=cp<=0x9FFF)}")

    # 3. 缩放 CN 字体到 2048 upem
    scale_cn_glyphs(font_cn, SCALE)
    font_cn['head'].unitsPerEm = 2048

    # 4. 将 CJK 字形从 CN 复制到 WarHelios
    glyf = font['glyf']
    glyf_cn = font_cn['glyf']
    hmtx = font['hmtx']
    hmtx_cn = font_cn['hmtx']
    glyph_order = list(font.getGlyphOrder())
    existing_names = set(glyph_order)
    cmap_tables = font['cmap'].tables

    replaced = 0
    added = 0

    for cp in sorted(cmap_cn.keys()):
        if not is_cjk(cp):
            continue

        cn_gn = cmap_cn[cp]
        if cn_gn not in glyf_cn:
            continue

        if cp in cmap_base:
            # WarHelios 已有该码点 -> 替换字形
            base_gn = cmap_base[cp]
            glyf[base_gn] = copy.deepcopy(glyf_cn[cn_gn])
            if cn_gn in hmtx_cn.metrics:
                hmtx[base_gn] = hmtx_cn.metrics[cn_gn]
            replaced += 1
        else:
            # 新增字形
            new_name = f"cn_{cp:04X}"
            if new_name in existing_names:
                continue
            glyf[new_name] = copy.deepcopy(glyf_cn[cn_gn])
            if cn_gn in hmtx_cn.metrics:
                hmtx[new_name] = hmtx_cn.metrics[cn_gn]
            glyph_order.append(new_name)
            existing_names.add(new_name)
            for tbl in cmap_tables:
                if hasattr(tbl, 'cmap') and tbl.format in (4, 12):
                    if tbl.format == 4 and cp > 0xFFFF:
                        continue
                    tbl.cmap[cp] = new_name
            added += 1

    print(f"    CJK: {replaced} 替换 + {added} 新增")

    font['maxp'].numGlyphs = len(glyph_order)
    font.setGlyphOrder(glyph_order)

    # 5. 度量保持 WarHelios
    font['OS/2'].usWeightClass = target_weight

    bmp = [cp for cp in list(cmap_base.keys()) + list(cmap_cn.keys()) if cp <= 0xFFFF]
    if bmp:
        font['OS/2'].usFirstCharIndex = min(bmp)
        font['OS/2'].usLastCharIndex = max(bmp)

    # 6. 名称表
    for rec in font['name'].names:
        if rec.platformID == 3 and rec.langID == 0x409:
            if rec.nameID in (1, 16):
                rec.string = "SrcHelios CN"
            elif rec.nameID == 4:
                rec.string = f"SrcHelios CN {weight_label}"
            elif rec.nameID == 6:
                rec.string = f"SrcHeliosCN-{weight_label}"
            elif rec.nameID in (2, 17):
                rec.string = weight_label
            elif rec.nameID == 10:
                rec.string = "WarHelios + Source Han Sans CN."

    # 7. 保存
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_name = f"SourceHanSansCN_WN_{weight_label}.ttf"
    out_path = os.path.join(OUTPUT_DIR, out_name)
    font.save(out_path)
    font.close()
    font_cn.close()

    # 验证
    fv = TTFont(out_path)
    cm = fv.getBestCmap()
    print(f"\n  保存: {out_name}")
    print(f"    字形数: {len(fv.getGlyphOrder())}")
    print(f"    upem: {fv['head'].unitsPerEm}")
    print(f"    CJK: {sum(1 for cp in cm if 0x4E00<=cp<=0x9FFF)}")
    print(f"    希腊: {sum(1 for cp in cm if 0x0370<=cp<=0x03FF)}")
    print(f"    度量: TypoAsc={fv['OS/2'].sTypoAscender}")
    fv.close()


def main():
    print("=" * 60)
    print("SrcHelios-CN 字体生成器 v2")
    print("基底: WarHelios + CJK: Source Han Sans CN (scaled to 2048)")
    print("=" * 60)

    for weight_label, war_name, cn_name, target_w in VARIANTS:
        build_srchelios(weight_label, war_name, cn_name, target_w)

    print(f"\n{'='*60}")
    print(f"完成！")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        sz = os.path.getsize(os.path.join(OUTPUT_DIR, f)) / 1024 / 1024
        print(f"  {f} ({sz:.1f}MB)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
