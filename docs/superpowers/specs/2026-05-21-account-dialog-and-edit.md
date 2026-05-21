# Account Add/Edit Dialog Design

## Goal
Replace the inline account add bar with a popup dialog, and add an edit button in the action column that only allows editing the date range.

## Changes

### 1. `AccountEditDialog` (new dialog)
- Single QDialog class with `mode` parameter: `'add'` or `'edit'`
- **Add mode**: QLineEdit (name) + QComboBox (date range) + OK/Cancel
- **Edit mode**: QLabel (name, read-only) + QComboBox (date range, pre-selected) + OK/Cancel
- Dark theme, consistent with existing UI

### 2. `AccountManagementPage`
- **Remove**: entire `add_card` (inline LineEdit + ComboBox + add button)
- **Add**: "添加公众号" PrimaryPushButton in the table title area (right side)
- **Action column**: add "编辑" PushButton alongside existing "删除" / "重试"
- `_on_add_account()` → opens `AccountEditDialog(mode='add')`
- `_on_edit_account(name)` → opens `AccountEditDialog(mode='edit', account_data)`

### 3. `Database.update_account_date_range(name, date_range)`
```sql
UPDATE wechat_account
SET date_range = ?, status = 'pending', updated_at = datetime('now','localtime')
WHERE name = ?
```
Resets status to `'pending'` so the background scraper re-fetches the account.

## Files changed
| File | Change |
|------|--------|
| `gui/pages/account_management_page.py` | Add dialog class, remove inline add bar, add edit btn |
| `spider/database.py` | Add `update_account_date_range` method |
