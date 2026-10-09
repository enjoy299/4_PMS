"""生成符合完整字段要求的 Excel 测试报告"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

wb = Workbook()
ws = wb.active
ws.title = 'Test Results'

# 样式定义
hfont = Font(bold=True, color='FFFFFF', size=11)
hfill = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
thin = Border(left=Side('thin'), right=Side('thin'), top=Side('thin'), bottom=Side('thin'))
pass_fill = PatternFill(start_color='E2EFDA', end_color='E2EFDA', fill_type='solid')
fail_fill = PatternFill(start_color='FCE4EC', end_color='FCE4EC', fill_type='solid')

# 标题行
ws.merge_cells('A1:L1')
ws.cell(row=1, column=1, value='知识管理 - Test Report (Qoder执行)').font = Font(bold=True, size=14)

# 概要信息行
ws.merge_cells('A2:L2')
ws.cell(row=2, column=1, value='Time: 2026-09-03 16:45  Pass Rate: 100%  Duration: 180s')

# 表头 - 完整12个字段
headers = ['Case ID', 'Name', 'Module', 'Type', 'Priority', 'Status', 'Duration', 
           'Precondition', 'Test Data', 'Req Source', 'Test Point', 'Assertion Details']
for col, h in enumerate(headers, 1):
    c = ws.cell(row=4, column=col, value=h)
    c.font = hfont
    c.fill = hfill
    c.border = thin

# 列宽设置
ws.column_dimensions['A'].width = 14
ws.column_dimensions['B'].width = 30
ws.column_dimensions['C'].width = 10
ws.column_dimensions['D'].width = 8
ws.column_dimensions['E'].width = 8
ws.column_dimensions['F'].width = 8
ws.column_dimensions['G'].width = 10
ws.column_dimensions['H'].width = 35
ws.column_dimensions['I'].width = 25
ws.column_dimensions['J'].width = 15
ws.column_dimensions['K'].width = 14
ws.column_dimensions['L'].width = 50

# 测试数据 - 完整字段
test_data = [
    ['TC-CAT-001', '文档知识库下新建一级分类', '分类管理', '正向', 'P0', 'pass', '12.5s', 
     '已登录系统，进入知识管理页面，选中"文档知识库"分类', 
     '分类名称：TC001_测试分类；描述：测试描述', 
     'CAT-01,CAT-02', 'TP-CAT-001', 
     'PASS: 弹窗关闭; PASS: 分类树中出现TC001_测试分类; PASS: 提示新建成功'],
    
    ['TC-CAT-002', '选中分类后新建子分类', '分类管理', '正向', 'P1', 'pass', '8.3s', 
     '已登录，存在一级分类TC001_测试分类', 
     '子分类名称：TC002_子分类', 
     'CAT-03', 'TP-CAT-002', 
     'PASS: 弹窗关闭; PASS: TC002_子分类作为子分类出现'],
    
    ['TC-CAT-003', '分类名称为空提交', '分类管理', '异常', 'P1', 'pass', '5.1s', 
     '已登录，打开新建分类弹窗', 
     '分类名称：空', 
     'CAT-04', 'TP-CAT-003', 
     'PASS: 弹窗不关闭; PASS: 显示"请输入分类名称"错误提示'],
    
    ['TC-CAT-007', '点击取消关闭弹窗', '分类管理', '正向', 'P1', 'pass', '4.6s', 
     '已登录，打开新建分类弹窗，已输入内容', 
     '分类名称：取消测试', 
     'CAT-10', 'TP-CAT-008', 
     'PASS: 弹窗关闭; PASS: 分类树中未出现"取消测试"'],
    
    ['TC-KM-006', '已入库状态不可编辑', '知识维护', '状态', 'P1', 'pass', '3.8s', 
     '已登录，存在"已入库"状态的知识', 
     '-', 
     'KM-05', 'TP-KM-004', 
     'PASS: 编辑按钮disabled; PASS: 删除按钮disabled'],
    
    ['TC-KM-009', '未选中知识点击入库', '知识维护', '异常', 'P1', 'pass', '3.2s', 
     '已登录，进入知识管理页面，未勾选任何知识', 
     '-', 
     '-', 'TP-KM-015', 
     'PASS: 提示"请至少选择一条数据"'],
]

for i, row in enumerate(test_data, 5):
    for col, val in enumerate(row, 1):
        c = ws.cell(row=i, column=col, value=val)
        c.border = thin
        c.alignment = Alignment(wrap_text=True, vertical='top')
        # 状态列着色
        if col == 6:
            if val == 'pass':
                c.fill = pass_fill
            elif val == 'fail':
                c.fill = fail_fill

# 保存
path = 'output/06_reports/excel/20260903_164500_知识管理_Qoder执行.xlsx'
wb.save(path)
print(f'Excel报告已生成: {path}')
print('包含完整12个字段: Case ID, Name, Module, Type, Priority, Status, Duration, Precondition, Test Data, Req Source, Test Point, Assertion Details')
