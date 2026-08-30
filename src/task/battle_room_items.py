# -*- coding: utf-8 -*-
"""
搜打撤道具类型 → 道具ID 自动解析

数据源(游戏工程 Json 表,非猜测):
  Item.json           全道具表(ID/NameL/Type/SubType...)
  SDCItem.json        搜打撤道具表(Type=16 的明细,210行)
  MultiLanguage.json  本地化表(NameL → 中文名)

规则: Type==16 即搜打撤道具,SubType 即装备分类:
  1护甲 2芯片 3增幅器 4藏品 5药品 6钥匙 7背包 8技能 11安全箱
每类取最小 ID 作为 GM 备料默认值;结果缓存到
configs/battle_room_item_ids.json,手动"GM道具ID映射"配置优先级更高。
"""

import json
import os

CLIENT_JSON_DIR = r'E:\Program\Client-Jump\Assets\Game\GameAsset\Config\GameConfig\Json'
CACHE_NAME = 'battle_room_item_ids.json'

SDC_ITEM_TYPE = 16          # Item.Type: 搜打撤道具
SUBTYPE_LABELS = {
    1: '护甲',
    2: '芯片',
    3: '增幅器',
    4: '藏品',
    5: '药品',
    6: '钥匙',
    7: '背包',
    8: '技能',
    9: '套装券',
    10: '钥匙链',
    11: '安全箱',
}
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _cache_path():
    return os.path.join(_PROJECT_ROOT, 'configs', CACHE_NAME)


def scan_client_tables(json_dir=CLIENT_JSON_DIR):
    """
    扫描游戏工程三张表,返回:
      mapping: {'护甲': 1600055, ...}   每类最小ID
      detail : [{'id','name','subtype'}] 全部 Type=16 行(升序)
    """
    items = _read_json(os.path.join(json_dir, 'Item.json'))
    sdc = _read_json(os.path.join(json_dir, 'SDCItem.json'))
    ml = _read_json(os.path.join(json_dir, 'MultiLanguage.json'))
    zh = {r['ID']: (r.get('Chinese') or r.get('Traditional') or '')
          for r in ml.values()}

    detail = []
    for srow in sdc.values():
        irow = items.get(str(srow['ID']))
        if not irow or irow.get('Type') != SDC_ITEM_TYPE:
            continue
        if irow.get('SubType') not in SUBTYPE_LABELS:
            continue
        detail.append({
            'id': int(irow['ID']),
            'name': zh.get(irow.get('NameL'), ''),
            'subtype': irow.get('SubType'),
            'value': srow.get('Value', 0),
            'season_value': srow.get('SeasonValue', 0),
        })
    detail.sort(key=lambda d: d['id'])

    mapping = {}
    for row in detail:
        label = SUBTYPE_LABELS[row['subtype']]
        # detail 已按 id 升序,首个即最小 ID(通常为最低品质)
        mapping.setdefault(label, row['id'])
    return mapping, detail


def load_snapshot(force=False, json_dir=CLIENT_JSON_DIR):
    """
    读取类型→ID 映射。优先缓存文件,缺失或 force 时重新扫描并写缓存。
    游戏工程不存在/解析失败时返回 ({}, []) 且不抛出(GM 备料退化为手动)。
    """
    cache = _cache_path()
    if not force and os.path.exists(cache):
        try:
            data = _read_json(cache)
            return data.get('mapping', {}), data.get('detail', [])
        except (OSError, ValueError):
            pass
    try:
        mapping, detail = scan_client_tables(json_dir)
    except (OSError, ValueError):
        return {}, []
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, 'w', encoding='utf-8') as f:
            json.dump({'mapping': mapping, 'detail': detail},
                      f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return mapping, detail


def names_for_subtype(detail, subtype):
    """某分类下全部道具名（用于 TIPS 标题匹配，替代关键词猜测）"""
    return [d['name'] for d in detail
            if d['subtype'] == subtype and d['name']]


def find_item_meta(detail, item_id):
    """按 ID 取道具元数据"""
    for d in detail:
        if d['id'] == int(item_id):
            return d
    return None


def merge_item_ids(auto_mapping, manual_json):
    """
    合成最终映射: 自动读取为底,用户"GM道具ID映射"(JSON串)覆盖同名键。
    Returns:
        (merged: dict, error: str 或 None)
    """
    merged = dict(auto_mapping or {})
    err = None
    raw = (manual_json or '').strip()
    if raw and raw != '{}':
        try:
            manual = json.loads(raw)
            if not isinstance(manual, dict):
                err = f'GM道具ID映射需为JSON对象,忽略: {raw!r}'
            else:
                merged.update({str(k): v for k, v in manual.items()})
        except ValueError as e:
            err = f'GM道具ID映射不是合法JSON({e}),已忽略'
    return merged, err


def main():
    import argparse
    parser = argparse.ArgumentParser(description='导出搜打撤道具类型→ID映射')
    parser.add_argument('--force', action='store_true', help='忽略缓存强制重扫')
    args = parser.parse_args()

    mapping, detail = load_snapshot(force=args.force)
    print(f'共 {len(detail)} 个 Type={SDC_ITEM_TYPE} 道具')
    for label in sorted(SUBTYPE_LABELS.values()):
        tid = mapping.get(label)
        names = [d['name'] for d in detail if SUBTYPE_LABELS[d['subtype']] == label]
        shown = [n for n in names if n][:2]
        print(f'  {label:<4} -> {tid}  {shown}')
    cache = _cache_path()
    print(f'缓存: {cache}')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
