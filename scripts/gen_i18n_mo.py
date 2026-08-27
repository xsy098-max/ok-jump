# -*- coding: utf-8 -*-
"""
编译界面翻译: i18n/zh_CN/LC_MESSAGES/ok.po -> ok.mo

ok-script 2.x 使用 gettext 加载应用翻译(1.x 的 translations.json 已不支持)。
编辑 .po 后运行本脚本;CI/开发可先 `pip install polib`(dev extra)。

用法:
    python scripts/gen_i18n_mo.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PO = ROOT / 'i18n' / 'zh_CN' / 'LC_MESSAGES' / 'ok.po'
MO = PO.with_suffix('.mo')


def main():
    try:
        import polib
    except ImportError:
        print('缺少 polib,请执行: pip install polib')
        return 1

    po = polib.pofile(str(PO))
    po.save_as_mofile(str(MO))
    print(f'已编译 {len(po)} 条翻译 -> {MO}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
