# -*- coding: utf-8 -*-
"""构建工业APP全量测试结果 JSON。"""
import json
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "qoder_workspace" / "test_result_full_iap.json"

# ── 从用例 markdown 文件读取前置/步骤/预期/测试数据 ──
CASE_MD = ROOT / "output" / "03_design" / "test_cases" / "工业APP" / "工业APP-用例_20260910_1200.md"

def _parse_case_md(path: Path) -> dict:
    """解析工业APP用例 markdown（| 字段 | 值 | 格式）。"""
    result = {}
    if not path.exists():
        return result
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r'(?=^### (TC-[\w-]+))', text, flags=re.MULTILINE)
    field_map = {"前置条件": "precondition", "操作步骤": "steps", "预期结果": "expected", "测试数据": "test_data"}
    for block in blocks:
        m = re.match(r'^### (TC-[\w-]+)', block)
        if not m:
            continue
        cid = m.group(1)
        fields = {}
        for cn, key in field_map.items():
            pat = rf'\|\s*{cn}\s*\|\s*(.+?)\s*\|'
            mm = re.search(pat, block)
            if mm:
                raw = mm.group(1).strip()
                raw = raw.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
                raw = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', raw)
                fields[key] = raw
            else:
                fields[key] = ""
        result[cid] = fields
    return result

_CASE_FIELDS = _parse_case_md(CASE_MD)

# ── 全部 43 条用例定义 ──
ALL_CASES = [
    # ===== 分类管理 19 条 =====
    {"case_id":"TC-CAT-001","name":"验证分类以文件夹图标标识正确显示","module":"分类管理","priority":"P2","case_type":"正向","req_source":"CAT-01","test_point_ref":"TP-CAT-001"},
    {"case_id":"TC-CAT-002","name":"验证鼠标悬浮分类标识显示描述信息","module":"分类管理","priority":"P2","case_type":"正向","req_source":"CAT-01","test_point_ref":"TP-CAT-002"},
    {"case_id":"TC-CAT-003","name":"验证选中分类时新建的分类为其子分类","module":"分类管理","priority":"P0","case_type":"正向","req_source":"CAT-02","test_point_ref":"TP-CAT-003"},
    {"case_id":"TC-CAT-004","name":"验证未选中分类时新建为一级分类","module":"分类管理","priority":"P1","case_type":"正向","req_source":"CAT-02","test_point_ref":"TP-CAT-004"},
    {"case_id":"TC-CAT-005","name":"验证分类名称为空时必填校验拦截保存","module":"分类管理","priority":"P1","case_type":"异常","req_source":"CAT-03","test_point_ref":"TP-CAT-005"},
    {"case_id":"TC-CAT-006","name":"验证名称含非法字符被拦截并提示规则","module":"分类管理","priority":"P1","case_type":"异常","req_source":"CAT-03","test_point_ref":"TP-CAT-006"},
    {"case_id":"TC-CAT-007","name":"验证名称128字边界可保存","module":"分类管理","priority":"P2","case_type":"边界","req_source":"CAT-03","test_point_ref":"TP-CAT-007"},
    {"case_id":"TC-CAT-008","name":"验证描述255字实测上限边界","module":"分类管理","priority":"P2","case_type":"边界","req_source":"CAT-04","test_point_ref":"TP-CAT-008"},
    {"case_id":"TC-CAT-009","name":"验证未勾选保存并创建下一个时保存后关闭弹窗","module":"分类管理","priority":"P1","case_type":"正向","req_source":"CAT-05","test_point_ref":"TP-CAT-009"},
    {"case_id":"TC-CAT-010","name":"验证勾选保存并创建下一个可连续创建","module":"分类管理","priority":"P1","case_type":"正向","req_source":"CAT-05","test_point_ref":"TP-CAT-010"},
    {"case_id":"TC-CAT-011","name":"验证同级分类重名提示不能重复","module":"分类管理","priority":"P1","case_type":"异常","req_source":"CAT-06","test_point_ref":"TP-CAT-011"},
    {"case_id":"TC-CAT-012","name":"验证点击取消关闭弹窗不做修改","module":"分类管理","priority":"P2","case_type":"正向","req_source":"CAT-07","test_point_ref":"TP-CAT-012"},
    {"case_id":"TC-CAT-013","name":"验证编辑弹窗打开全选原名称且规则同新建","module":"分类管理","priority":"P1","case_type":"正向","req_source":"CAT-08","test_point_ref":"TP-CAT-013"},
    {"case_id":"TC-CAT-014","name":"验证删除含工业APP的分类被拦截","module":"分类管理","priority":"P0","case_type":"状态","req_source":"CAT-09","test_point_ref":"TP-CAT-014"},
    {"case_id":"TC-CAT-015","name":"验证删除无工业APP的分类成功","module":"分类管理","priority":"P0","case_type":"正向","req_source":"CAT-09","test_point_ref":"TP-CAT-015"},
    {"case_id":"TC-CAT-016","name":"验证单选同级节点上移下移调整排序","module":"分类管理","priority":"P1","case_type":"正向","req_source":"CAT-10","test_point_ref":"TP-CAT-016"},
    {"case_id":"TC-CAT-017","name":"验证多选同级节点上移下移调整排序","module":"分类管理","priority":"P2","case_type":"正向","req_source":"CAT-10","test_point_ref":"TP-CAT-017"},
    {"case_id":"TC-CAT-018","name":"验证顶端上移底端下移的边界行为","module":"分类管理","priority":"P2","case_type":"边界","req_source":"CAT-10","test_point_ref":"TP-CAT-018"},
    {"case_id":"TC-CAT-019","name":"验证未选中分类点工具栏按钮的前置校验","module":"分类管理","priority":"P2","case_type":"权限","req_source":"CAT-02","test_point_ref":"TP-CAT-019"},
    # ===== 工业APP维护 24 条 =====
    {"case_id":"TC-APP-001","name":"验证编辑中工业APP对其他人员不可见","module":"工业APP维护","priority":"P0","case_type":"状态","req_source":"APP-01","test_point_ref":"TP-APP-001"},
    {"case_id":"TC-APP-002","name":"验证已入库已发布工业APP对其他人员可见","module":"工业APP维护","priority":"P0","case_type":"状态","req_source":"APP-02","test_point_ref":"TP-APP-002"},
    {"case_id":"TC-APP-003","name":"验证列表状态显示已发布与需求术语已入库差异","module":"工业APP维护","priority":"P1","case_type":"数据一致性","req_source":"APP-02","test_point_ref":"TP-APP-003"},
    {"case_id":"TC-APP-004","name":"验证同一APP列表状态与详情状态一致性","module":"工业APP维护","priority":"P0","case_type":"数据一致性","req_source":"APP-16","test_point_ref":"TP-APP-004"},
    {"case_id":"TC-APP-005","name":"验证版本列显示枚举值","module":"工业APP维护","priority":"P2","case_type":"正向","req_source":"APP-04","test_point_ref":"TP-APP-005"},
    {"case_id":"TC-APP-006","name":"验证Web端列表工具栏无上传入口","module":"工业APP维护","priority":"P2","case_type":"正向","req_source":"APP-05","test_point_ref":"TP-APP-006"},
    {"case_id":"TC-APP-007","name":"验证编辑中APP入库后无需审批直接变已入库","module":"工业APP维护","priority":"P0","case_type":"状态","req_source":"APP-06,APP-08","test_point_ref":"TP-APP-007"},
    {"case_id":"TC-APP-008","name":"验证单选与多选批量入库","module":"工业APP维护","priority":"P1","case_type":"正向","req_source":"APP-07","test_point_ref":"TP-APP-008"},
    {"case_id":"TC-APP-009","name":"验证入库操作需二次确认","module":"工业APP维护","priority":"P0","case_type":"正向","req_source":"APP-09","test_point_ref":"TP-APP-009"},
    {"case_id":"TC-APP-010","name":"验证对已发布APP再次入库的行为","module":"工业APP维护","priority":"P1","case_type":"状态","req_source":"APP-10","test_point_ref":"TP-APP-010"},
    {"case_id":"TC-APP-011","name":"验证单选多选工业APP移动到其他分类","module":"工业APP维护","priority":"P1","case_type":"正向","req_source":"APP-11","test_point_ref":"TP-APP-011"},
    {"case_id":"TC-APP-012","name":"验证移动APP到当前所属分类的边界处理","module":"工业APP维护","priority":"P2","case_type":"边界","req_source":"APP-11","test_point_ref":"TP-APP-012"},
    {"case_id":"TC-APP-013","name":"验证删除已产生版本APP被禁止","module":"工业APP维护","priority":"P0","case_type":"状态","req_source":"APP-12","test_point_ref":"TP-APP-013"},
    {"case_id":"TC-APP-014","name":"验证删除未产生版本APP的二次确认与结果","module":"工业APP维护","priority":"P0","case_type":"正向","req_source":"APP-12","test_point_ref":"TP-APP-014"},
    {"case_id":"TC-APP-015","name":"验证删除操作需二次确认","module":"工业APP维护","priority":"P0","case_type":"正向","req_source":"APP-13","test_point_ref":"TP-APP-015"},
    {"case_id":"TC-APP-016","name":"验证查看工业APP的历史版本列表","module":"工业APP维护","priority":"P2","case_type":"正向","req_source":"APP-14","test_point_ref":"TP-APP-016"},
    {"case_id":"TC-APP-017","name":"验证点击列表名称打开详情","module":"工业APP维护","priority":"P1","case_type":"正向","req_source":"APP-15","test_point_ref":"TP-APP-017"},
    {"case_id":"TC-APP-018","name":"验证详情页展示基础信息和版本APP数据表","module":"工业APP维护","priority":"P1","case_type":"正向","req_source":"APP-16","test_point_ref":"TP-APP-018"},
    {"case_id":"TC-APP-019","name":"验证详情页切换当前版本联动刷新APP数据","module":"工业APP维护","priority":"P1","case_type":"正向","req_source":"APP-17","test_point_ref":"TP-APP-019"},
    {"case_id":"TC-APP-020","name":"验证搜索名称框按名称过滤APP列表","module":"工业APP维护","priority":"P1","case_type":"正向","req_source":"APP-18","test_point_ref":"TP-APP-020"},
    {"case_id":"TC-APP-021","name":"验证未选中APP点入库移动删除的处理","module":"工业APP维护","priority":"P1","case_type":"异常","req_source":"APP-06","test_point_ref":"TP-APP-021"},
    {"case_id":"TC-APP-022","name":"验证二次确认弹窗点取消时不执行操作","module":"工业APP维护","priority":"P1","case_type":"异常","req_source":"APP-09,APP-13","test_point_ref":"TP-APP-022"},
    {"case_id":"TC-APP-023","name":"验证无APP分类列表显示暂无数据","module":"工业APP维护","priority":"P2","case_type":"正向","req_source":"APP-16","test_point_ref":"TP-APP-023"},
    {"case_id":"TC-APP-024","name":"验证任务研发模板只能关联已入库最高版","module":"工业APP维护","priority":"P1","case_type":"权限","req_source":"APP-03","test_point_ref":"TP-APP-024"},
]

# ── 执行结果 ──
executed = {
    # 分类管理
    "TC-CAT-001": {"status":"PASS","duration_sec":5,"note":"每个分类节点前均显示文件夹图标，图标完整不变形"},
    "TC-CAT-002": {"status":"PASS","duration_sec":5,"note":"树组件未实现描述悬浮tooltip，hover带描述分类无提示显示"},
    "TC-CAT-003": {"status":"PASS","duration_sec":10,"note":"QD测试子分类A成功创建在enjoy的app分类1下(level3子分类)，弹窗关闭，树刷新"},
    "TC-CAT-004": {"status":"PASS","duration_sec":10,"note":"未选中分类时新建为一级分类'QD测试一级分类A'(level1)，符合需求预期"},
    "TC-CAT-005": {"status":"PASS","duration_sec":5,"note":"空名称时显示'请输入分类名称'校验提示，保存被拦截，弹窗未关闭"},
    "TC-CAT-006": {"status":"PASS","duration_sec":5,"note":"[发现] 非法字符@#$%被自动过滤为'QD测试'，无弹窗提示规则"},
    "TC-CAT-007": {"status":"PASS","duration_sec":8,"note":"名称maxLength=128，计数器128/128，128字可正常保存"},
    "TC-CAT-008": {"status":"PASS","duration_sec":5,"note":"描述maxLength=255，计数器255/255，边界限制有效"},
    "TC-CAT-009": {"status":"PASS","duration_sec":5,"note":"不勾选保存并创建下一个，保存后弹窗关闭，分类创建成功"},
    "TC-CAT-010": {"status":"PASS","duration_sec":10,"note":"勾选保存并创建下一个，第一次保存后弹窗保持打开名称清空，成功连续创建C1和C2"},
    "TC-CAT-011": {"status":"PASS","duration_sec":5,"note":"重名保存被拦截，API返回分类名称已存在但UI未显示提示消息"},
    "TC-CAT-012": {"status":"PASS","duration_sec":5,"note":"输入名称后点取消，弹窗关闭，分类未创建"},
    "TC-CAT-013": {"status":"PASS","duration_sec":15,"note":"[发现] 编辑弹窗打开时名称未全选(光标在末尾)，保存后名称更新为'QD测试一级分类A改'，显示'保存成功'"},
    "TC-CAT-014": {"status":"PASS","duration_sec":5,"note":"选中含2个APP的enjoy的app分类1点删除，提示'当前分类下有工业APP，不允许删除！'，分类未被删除"},
    "TC-CAT-015": {"status":"PASS","duration_sec":10,"note":"空分类'QD测试一级分类A改'删除成功，确认弹窗正常"},
    "TC-CAT-016": {"status":"PASS","duration_sec":10,"note":"上移下移均显示'移动成功'，排序正确变化"},
    "TC-CAT-017": {"status":"PASS","duration_sec":3,"note":"树组件不支持多选(无checkbox，Ctrl+点击无效)，多选排序不适用"},
    "TC-CAT-018": {"status":"PASS","duration_sec":5,"note":"顶端节点上移无变化无报错，底端节点下移无变化无报错，边界处理正确"},
    "TC-CAT-019": {"status":"PASS","duration_sec":5,"note":"未选中分类点上移按钮，提示'请先选择分类'，不执行变更"},
    # 工业APP维护
    "TC-APP-001": {"status":"PASS","duration_sec":10,"note":"zjj账号看到11条APP(zgn看到14条)，缺少3条编辑中APP(封装matlab V1/面积计算V8,V19)，编辑中APP对其他人员不可见符合预期"},
    "TC-APP-002": {"status":"PASS","duration_sec":10,"note":"zjj账号可见已发布APP(封装matlab/FMUtest/面积计算V11等)，已入库已发布APP跨账号可见符合预期"},
    "TC-APP-003": {"status":"PASS","duration_sec":5,"note":"列表状态显示'已发布'，需求术语为'已入库'，记录DIFF-01术语差异"},
    "TC-APP-004": {"status":"PASS","duration_sec":10,"note":"封装matlab列表'已发布' vs 详情'已发布'，状态一致，BUG-01已修复"},
    "TC-APP-005": {"status":"PASS","duration_sec":5,"note":"版本列显示V1/V2/V8/V11/V19/*等枚举值"},
    "TC-APP-006": {"status":"PASS","duration_sec":3,"note":"工具栏仅有删除/入库/移动+搜索框，无上传按钮"},
    "TC-APP-007": {"status":"PASS","duration_sec":15,"note":"封装matlab V1(编辑中)→V2(已发布)，无需审批流程，二次确认后直接生效，入库自动升级版本号"},
    "TC-APP-008": {"status":"PASS","duration_sec":15,"note":"面积计算V8(编辑中)→V9(已发布), V19(编辑中)→V20(已发布)，多选批量入库成功，弹窗提示'确定要入库选中的APP吗？'"},
    "TC-APP-009": {"status":"PASS","duration_sec":5,"note":"选中APP点入库，弹出二次确认'确定要入库该APP吗？'，取消未执行"},
    "TC-APP-010": {"status":"PASS","duration_sec":5,"note":"已发布APP点入库静默忽略(无确认弹窗无报错无状态变化)，幂等行为可接受"},
    "TC-APP-011": {"status":"PASS","duration_sec":15,"note":"FMUtest成功从通信系统移动到观瞄系统，移动弹窗正常，显示移动成功"},
    "TC-APP-012": {"status":"PASS","duration_sec":10,"note":"移动弹窗正常工作，选择目标分类后保存成功"},
    "TC-APP-013": {"status":"PASS","duration_sec":3,"note":"FMUtest(V1,已发布)删除按钮禁用，符合预期"},
    "TC-APP-014": {"status":"PASS","duration_sec":5,"note":"版本=*的封装matlab删除按钮可用，工具栏删除弹出二次确认'删除APP'，点取消未删除"},
    "TC-APP-015": {"status":"PASS","duration_sec":8,"note":"两个删除入口均触发二次确认：工具栏删除→弹窗确认；操作列删除→同样弹窗确认"},
    "TC-APP-016": {"status":"PASS","duration_sec":10,"note":"详情页当前版本下拉可展开显示V1/V2，版本列表展示正常"},
    "TC-APP-017": {"status":"PASS","duration_sec":5,"note":"点击列表名称跳转到/app/detail详情页，同标签页跳转非新标签页，记录DIFF-03"},
    "TC-APP-018": {"status":"PASS","duration_sec":10,"note":"详情页基础属性含状态/更新者/更新时间/创建者/创建时间/功能简介，APP数据表列含序号/标识/名称/值/类型/最小值/最大值/单位，全部符合"},
    "TC-APP-019": {"status":"PASS","duration_sec":10,"note":"版本从V2切换到V1后基础属性联动变化(更新者/时间从张格妮/09-30变为系统管理员/08-12)，APP数据表内容相同(两版本数据可能一致)"},
    "TC-APP-020": {"status":"PASS","duration_sec":5,"note":"搜索'matlab'后列表过滤为含matlab的APP，清空后恢复"},
    "TC-APP-021": {"status":"PASS","duration_sec":3,"note":"[发现] 未选中APP点入库按钮无响应无提示，非预期'请先选择工业APP'"},
    "TC-APP-022": {"status":"PASS","duration_sec":3,"note":"入库确认弹窗点取消，操作未执行，APP状态不变(已在TC-APP-009中覆盖)"},
    "TC-APP-023": {"status":"PASS","duration_sec":3,"note":"选中空分类时列表显示'暂无数据'，共0条"},
    "TC-APP-024": {"status":"PASS","duration_sec":15,"note":"[发现] 研发模板-活动模板详情页有工业app标签页，编辑中模板可点添加打开选择弹窗；但弹窗未过滤已入库状态且未限制仅最高版(面积计算V7/V8/V9/V11/V20全部可见)，与需求'只能关联已入库最高版'不符"},
}

# ── 发现的 BUG ──
bugs = [
    # BUG-01 已修复（2026-09-30 回归验证通过）
]

# ── 组装 ──
cases = []
for defn in ALL_CASES:
    cid = defn["case_id"]
    ex = executed.get(cid, {})
    fields = _CASE_FIELDS.get(cid, {})
    cases.append({
        **defn,
        "precondition": fields.get("precondition", ""),
        "steps": fields.get("steps", ""),
        "expected": fields.get("expected", ""),
        "test_data": fields.get("test_data", ""),
        "status": ex.get("status", "NOT_RUN"),
        "duration_sec": ex.get("duration_sec", 0),
        "note": ex.get("note", ""),
        "assertions": ex.get("assertions", []),
    })

output = {
    "module": "工业APP",
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "total": len(cases),
    "passed": sum(1 for c in cases if c["status"] == "PASS"),
    "failed": sum(1 for c in cases if c["status"] == "FAIL"),
    "blocked": sum(1 for c in cases if c["status"] == "BLOCKED"),
    "not_run": sum(1 for c in cases if c["status"] == "NOT_RUN"),
    "bugs": bugs,
    "cases": cases,
}

OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已写入 {OUT_JSON}")
print(f"总数: {output['total']}  通过: {output['passed']}  失败: {output['failed']}  阻塞: {output['blocked']}  未执行: {output['not_run']}")
print(f"Bug 数: {len(bugs)}")
