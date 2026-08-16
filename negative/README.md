# 负向编译测试（必须失败的用例）

每个 `cases/*.frond` 是一个完整入口程序，**必须以 exit code 1 失败**，且诊断信息须包含
文件首行 `// EXPECT:` 声明的子串。运行：

```bash
bash run.sh
```

用例命名：`<主题>_<场景>.frond`。新增用例时同步在 BUG_REPORT.md 登记 bug 编号。

## 覆盖的 bug

- `missing_return_*` — Bug #89：非 void 返回类型必须有尾表达式或 return/throw
- `lambda_*` — lambda 强制 `: T` 返回类型标注；lambda 内 return 按 lambda 自身类型检查（Bug #91）
- `propagate_*` — `?` 传播运算符仅用于 Nullable/Throw
- `match_*` — match 穷尽性
- `user_ffi_*` — FFI 权限分层（`@extern`/`#{ }#` 仅 stdlib）
- `overflow_*` — 字面量超出类型范围（Bug #21）
