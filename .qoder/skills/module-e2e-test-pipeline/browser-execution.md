# 浏览器执行手册（阶段 9）

用 `browser-use` MCP 真实执行 `qoder_workspace/test_plan_<MODULE>.md` 里的用例。**首次调用某 MCP 工具前，必须在本会话读过它的 JSON schema**（`…/mcps/browser-use/tools/<tool>.json`）。常用：`list_pages / navigate_page / take_snapshot / evaluate_script / click / take_screenshot`。

## 执行节奏

1. `navigate_page` 到模块入口页（如 `/industrialApp`）。
2. **只读类**用例：一次 `evaluate_script` 批量提取页面事实（列名、行数据、分页、按钮集合、状态值）。
3. **交互类**用例：按 `打开弹窗 → 设置输入 → 保存 → 校验反馈` 模式；**点击与读取分两次调用**（`evaluate_script` 同步返回，Vue/EP 弹窗是异步渲染）。
4. 每个子模块/关键用例 `take_screenshot` 存证到 `output/06_reports/screenshots/<MODULE>_NN.png`。

## 可复用代码片段（evaluate_script 的 function 体内）

### A. 瞬时 toast 全局捕获（最重要）
Element Plus 的 `.el-message`/`.el-message-box` 约 3s 自动消失，异步读取/截图会漏。**先注入一次**，之后所有提示都留痕，事后再读 `window.__capturedToasts`：
```js
if (!window.__toastObserver) {
  window.__capturedToasts = [];
  window.__toastObserver = new MutationObserver(muts => {
    for (const m of muts) for (const n of m.addedNodes) {
      if (n.nodeType === 1 && (n.matches('.el-message') || n.matches('.el-message-box'))) {
        window.__capturedToasts.push((n.innerText || '').trim());
      }
    }
  });
  window.__toastObserver.observe(document.body, { childList: true, subtree: true });
}
return { installed: true, count: window.__capturedToasts.length };
```
读取并清空：`const t = window.__capturedToasts.slice(); window.__capturedToasts.length = 0; return t;`

### B. Element Plus 输入框赋值（触发 v-model）
`fill`/`type_text` 对 EP 常不触发校验/绑定。用原生 setter + input 事件：
```js
function setVal(input, val) {
  const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(input, val);
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}
// 例：给弹窗内某输入框赋值
const dlg = [...document.querySelectorAll('.el-overlay')].find(o => getComputedStyle(o).display !== 'none');
const input = dlg.querySelector('input[placeholder*="名称"], .el-input__inner');
setVal(input, 'QD测试分类');
return { ok: !!input, value: input?.value };
```

### C. 弹窗可见性判断（用 overlay，不要用 dialog）
```js
const overlays = [...document.querySelectorAll('.el-overlay')].filter(o => getComputedStyle(o).display !== 'none');
const open = overlays.length > 0;
const title = overlays[0]?.querySelector('.el-dialog__title, .el-message-box__title')?.innerText?.trim() || '';
return { open, title };   // .el-dialog 自身 display 恒为 block，不可靠
```

### D. 点击按钮：区分工具栏 vs 行级；MCP click 失败时用 JS 兜底
```js
// 只点“不在表格单元格内”的按钮 = 顶部工具栏按钮（行级按钮在 <td> 内）
const btns = [...document.querySelectorAll('button')].filter(b => !b.closest('td'));
const target = btns.find(b => (b.innerText || '').trim() === '删除');
target?.click();
return { clicked: !!target, toolbarBtns: btns.map(b => (b.innerText||'').trim()).filter(Boolean) };
```
> MCP `click` 报 “does not match a single element”（selector 命中多个）或 “Element is not visible” 时，改用上面的 `evaluate_script` + 文本/结构过滤精确定位再 `.click()`。

### E. el-select 下拉选择
```js
// 1) 展开：点 select 触发器；2) 点选项（分两次调用，等异步渲染）
document.querySelector('.el-select .el-input__inner, .el-select__wrapper')?.click();
// 下一次调用：
const opt = [...document.querySelectorAll('.el-select-dropdown__item')].find(i => (i.innerText||'').trim() === '目标分类');
opt?.click(); return { picked: !!opt };
```

### F. 只读事实批量提取（列名/行/分页/按钮）
```js
const wrap = document.querySelector('.el-table');
const cols = [...document.querySelectorAll('.el-table__header th .cell')].map(e => e.innerText.trim()).filter(Boolean);
const rows = [...document.querySelectorAll('.el-table__body tr')].map(tr => [...tr.querySelectorAll('td .cell')].map(td => td.innerText.trim()));
const pager = document.querySelector('.el-pagination__total')?.innerText?.trim() || '';
return { cols, rowCount: rows.length, firstRows: rows.slice(0,3), pager };
```

## 有副作用用例的安全策略（数据自洽原则）

**数据自洽**：优先**自建→自操作→自清理**，全程不污染现有数据；自建不了的**借用账号现有数据**只做只读/可还原操作；绝不破坏共享数据；结束校验残留为空。

| 操作 | 策略 |
|---|---|
| 可自建（分类/知识/项目等） | 用带唯一前缀的测试数据（如 `QD测试*`）**自己建→自己编辑/上移/下移/删除**全程自操作，跑完全部删除，`evaluate_script` 校验残留为空 |
| 不可自建但账号已有（如 Web 无上传入口的工业APP） | **借用现有数据**做只读或可还原操作验证（选中/查看/详情/移动后移回）；不做破坏性变更 |
| 删除共享数据（真实 APP/他人数据） | 只走 **确认框→取消**，不真删；仍可用 toast 验证按钮行为（如“只有未产生过版本的数据才可以删除”） |
| 移动/入库等状态变更 | 执行后**还原**（A→B 再 B→A）；无法还原的记入主报告清理说明 |
| 自建与借用都无法覆盖 | 才判 **BLOCKED**（如缺“编辑中”状态、多版本、第二账号、跨模块界面），写清阻塞根因与复测前置 |

## BLOCKED 判定与记录

仅当**自建**与**安全借用现有数据**都无法覆盖该用例时才判 BLOCKED（缺数据/缺权限/跨模块依赖/组件限制），不伪造 pass/fail。逐条记录：用例 ID、阻塞根因、复测所需前置样本。这些进主报告“BLOCKED 专章”，并在 `results` 里映射为 `manual`（见 report-generation.md）。

## 截图存证

关键状态 `take_screenshot` 存到 `output/06_reports/screenshots/`，命名 `<MODULE>_NN.png`（NN 递增），并在主报告引用。截图**不能替代** toast 文本捕获（提示消失快），两者并用。
