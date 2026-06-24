"""
SrcWagon / SrcHelios 发布包生成器
- 各字体独立版本号（基于输入文件的最新 git commit 日期）
- 已打包且版本一致的字体跳过
- 上传到 S3 兼容存储（固定路径）
- 生成 metadata.json
"""

import os
import sys
import json
import hashlib
import shutil
import subprocess
from pathlib import Path

import py7zr

WORKSPACE_DIR = Path(__file__).resolve().parent
RELEASES_DIR = WORKSPACE_DIR / "Releases"
OUTPUT_DIR = WORKSPACE_DIR / "dist"
BASE_DIR = WORKSPACE_DIR / "base"
CN_FONTS_DIR = Path(r"C:\Users\HoloI\Documents\dev\lesta\ships\mods\SrcWagon\SrcWagonCHS\SrcWagon\Common\res_mods\gui\fonts")

# 字体项目：(源目录, 输出7z前缀, metadata键名, 版本相关输入路径列表)
FONT_PROJECTS = [
    {
        "key": "SrcWagon-MainlandCN",
        "src": RELEASES_DIR / "SrcWagon-CN" / "fonts",
        "inputs": [
            BASE_DIR / "ALS_Wagon",
            BASE_DIR / "SourceHanSans" / "SourceHanSansSC-VF.ttf",
            WORKSPACE_DIR / "build_all.py",
        ],
    },
    {
        "key": "SrcWagon-TWProvince",
        "src": RELEASES_DIR / "SrcWagon-TW" / "fonts",
        "inputs": [
            BASE_DIR / "ALS_Wagon",
            BASE_DIR / "SourceHanSans" / "SourceHanSansTC-VF.ttf",
            WORKSPACE_DIR / "build_all.py",
        ],
    },
    {
        "key": "SrcWagon-HKSAR",
        "src": RELEASES_DIR / "SrcWagon-HK" / "fonts",
        "inputs": [
            BASE_DIR / "ALS_Wagon",
            BASE_DIR / "SourceHanSans" / "SourceHanSansHC-VF.ttf",
            WORKSPACE_DIR / "build_all.py",
        ],
    },
    {
        "key": "SrcWagon-JP",
        "src": RELEASES_DIR / "SrcWagon-JP" / "fonts",
        "inputs": [
            BASE_DIR / "ALS_Wagon",
            BASE_DIR / "SourceHanSans" / "SourceHanSansJP-VF.ttf",
            WORKSPACE_DIR / "build_all.py",
        ],
    },
    {
        "key": "SrcHelios-MainlandCN",
        "src": WORKSPACE_DIR / "SrcHelios-CN" / "gui" / "fonts",
        "inputs": [
            BASE_DIR / "WarHelios",
            CN_FONTS_DIR,
            WORKSPACE_DIR / "build_srchelios.py",
        ],
    },
]


# ============================================================
# 版本号：取一组输入路径中最新的 git commit 日期
# ============================================================

def get_latest_date(paths):
    """从一组路径中找出最新的 git commit 日期"""
    latest = None
    for p in paths:
        if p.is_dir():
            # 目录：取目录本身及其下所有文件的 git log
            search_path = str(p)
        else:
            search_path = str(p)

        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ci", "--", search_path],
                capture_output=True, text=True, cwd=WORKSPACE_DIR,
            )
            date_str = result.stdout.strip()
            if date_str:
                d = date_str.split()[0]  # "2026-06-24"
                if not latest or d > latest:
                    latest = d
        except:
            pass

    if latest:
        parts = latest.split("-")
        return f"{int(parts[0]) % 100}.{int(parts[1])}.{int(parts[2])}"

    # 回退：用本文件 mtime
    import datetime
    mtime = os.path.getmtime(__file__)
    dt = datetime.datetime.fromtimestamp(mtime)
    return f"{dt.year % 100}.{dt.month}.{dt.day}"


# ============================================================
# 工具函数
# ============================================================

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_existing_metadata():
    """读取已有的 metadata.json"""
    path = WORKSPACE_DIR / "metadata.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": "", "fonts": {}}


def pack_one(meta_key, fonts_src):
    """打包 gui/fonts/ 结构的 7z，返回路径"""
    if not fonts_src.is_dir():
        return None

    temp_dir = WORKSPACE_DIR / f"_pkg_{meta_key}"
    target_dir = temp_dir / "gui" / "fonts"
    target_dir.mkdir(parents=True, exist_ok=True)

    for f in sorted(fonts_src.glob("*.ttf")):
        shutil.copy2(f, target_dir / f.name)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    arc_path = OUTPUT_DIR / f"{meta_key}.7z"

    with py7zr.SevenZipFile(arc_path, "w") as archive:
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                full = Path(root) / f
                archive.write(str(full), str(full.relative_to(temp_dir)))

    shutil.rmtree(temp_dir, ignore_errors=True)
    return arc_path


def upload_to_r2(local_path, remote_key):
    endpoint = os.environ.get("R2_ENDPOINT")
    bucket = os.environ.get("R2_BUCKET")
    access_key = os.environ.get("R2_ACCESS_KEY")
    secret_key = os.environ.get("R2_SECRET_KEY")

    if not all([endpoint, bucket, access_key, secret_key]):
        print(f"  [跳过上传] R2 环境变量未完整配置")
        return False

    remote = f"s3://{bucket}/fonts/{remote_key}"
    print(f"  上传: {remote_key} ...", end=" ", flush=True)

    result = subprocess.run([
        "aws", "s3", "cp", str(local_path), remote,
        "--endpoint-url", endpoint,
    ], capture_output=True, text=True,
       env={
           **os.environ,
           "AWS_ACCESS_KEY_ID": access_key,
           "AWS_SECRET_ACCESS_KEY": secret_key,
           "AWS_DEFAULT_REGION": "auto",
       })

    if result.returncode == 0:
        print("OK")
        return True
    else:
        print(f"失败\n{result.stderr}")
        return False


def trigger_deploy_hook():
    hook_url = os.environ.get("CF_PAGES_DEPLOY_HOOK")
    if not hook_url:
        print("  [跳过 deploy] CF_PAGES_DEPLOY_HOOK 未设置")
        return False

    print(f"  触发 Cloudflare Pages 部署 ...", end=" ", flush=True)
    result = subprocess.run(
        ["curl", "-X", "POST", hook_url],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("OK")
        return True
    else:
        print(f"失败\n{result.stderr}")
        return False


# ============================================================
# 主流程
# ============================================================

def main():
    ci_mode = "--ci" in sys.argv
    existing = load_existing_metadata()
    metadata = {"version": existing.get("version", ""), "fonts": {}}
    built = 0
    skipped = 0

    print("=" * 60)
    if ci_mode:
        print("  SrcWagon CI 发布 (仅上传 + 元数据)")
    else:
        print("  SrcWagon 发布包生成器")
    print("=" * 60)

    for proj in FONT_PROJECTS:
        key = proj["key"]
        arc_path = OUTPUT_DIR / f"{key}.7z"

        # CI 模式：7z 必须已存在（本地打包提交），只上传 + 写元数据
        if ci_mode:
            if not arc_path.exists():
                print(f"\n  [{key}] 跳过: {arc_path.name} 不存在")
                continue

            version = existing.get("fonts", {}).get(key, {}).get("version", "?")
            file_hash = sha256_file(arc_path)
            file_size = arc_path.stat().st_size

            print(f"\n  [{key}] v{version} {file_size/1024/1024:.1f}MB  sha256={file_hash[:16]}...")
            upload_to_r2(arc_path, f"{key}.7z")
            metadata["fonts"][key] = {"version": version, "sha256": file_hash}
            built += 1
            continue

        # 本地模式：完整流程
        fonts_src = proj["src"]
        if not fonts_src.is_dir():
            print(f"\n  [{key}] 跳过: 源目录不存在")
            continue

        # 取版本号
        version = get_latest_date(proj["inputs"])

        # 检查是否需要跳过（已打包且版本一致）
        prev = existing.get("fonts", {}).get(key, {})
        if arc_path.exists() and prev.get("version") == version:
            print(f"\n  [{key}] v{version} 未变更, 跳过")
            metadata["fonts"][key] = prev
            skipped += 1
            continue

        # 打包
        print(f"\n  [{key}] v{version}", end=" ", flush=True)
        arc_path = pack_one(key, fonts_src)
        if not arc_path or not arc_path.exists():
            print("打包失败")
            continue

        file_hash = sha256_file(arc_path)
        file_size = arc_path.stat().st_size
        print(f"{file_size/1024/1024:.1f}MB  sha256={file_hash[:16]}...")

        upload_to_r2(arc_path, f"{key}.7z")
        metadata["fonts"][key] = {"version": version, "sha256": file_hash}
        built += 1

    # 写入 metadata.json
    meta_path = WORKSPACE_DIR / "metadata.json"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    trigger_deploy_hook()

    print(f"\n{'='*60}")
    print(f"  完成：已打包 {built} 个，跳过 {skipped} 个")
    print(f"  元数据: {meta_path}")
    for key, info in metadata["fonts"].items():
        print(f"    {key}: v{info.get('version','?')}  sha256={info.get('sha256','?')[:16]}...")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
