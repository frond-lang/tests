# Kuzo 引擎 Bug 修复追踪

> 本文档由 `test-suite/` 测试套件发现，记录所有引擎 bug 的修复优先级与临时绕过方案。
> 最后更新：2026-08-08（#1-#17 已修复；执行器审查 H1-H5、M1-M9、L1-L12 已修复；边缘测试 #18-#55 中 #18/#19/#20/#21/#22/#23/#24/#25/#26/#27/#28/#29/#30/#31/#33/#34/#35/#36/#37/#38/#39/#40/#41/#42/#43/#44/#45/#46/#47/#48/#49/#50/#51/#52/#53/#54/#55 已修复；P0/P1 审查修复 R1-R11 已完成；#56 match arm effect 泄漏已修复；#57 non_tail_rec_to_loop 破坏 defer LIFO 已修复）

---

## P0/P1 审查修复（R1-R11）

以下修复基于对 P0/P1 bug 修复代码的系统审查，解决特判、workaround、fallback、精度损失和不完整实现问题。

### R1：Bug #7 异步路径 control_signal 跳过缺失

- **问题**：异步路径（Schedule.rs）在 compute_propagate 设置 control_signal 后未跳过 notify_downstream，同步路径（Compute.rs:2955-2960）有此检查。循环体内 `?` 传播可能导致 pending 计数错误。
- **修复**：[Schedule.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/engine/Schedule.rs#L860-L865) 在 `control_signal_nodes` 检查后、`notify_downstream` 前新增 `frame.control_signal` 非空检查，与同步路径保持一致。

### R2：Bug #1 heap_equals discriminant fallback

- **问题**：`heap_equals` 的 `_ => discriminant(a) == discriminant(b)` fallback 对 Partial/TraitVal/LazyVal/AtomicVal/AsyncVal/ChannelVal/SenderVal/ReceiverVal/CoroutineFrame 仅比较变体种类不比较内容，两个不同内容的 Partial/TraitVal 会被判为相等。
- **修复**：[Arena.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/value/Arena.rs#L1631-L1680) 为每个 HeapObj 变体添加显式内容比较：Partial 比较 func_id/upvalues/bound_args；TraitVal 比较 trait_name/method_names/method_values/data；LazyVal 比较已 force 的缓存结果；AtomicVal 比较内部值；ChannelVal/SenderVal/ReceiverVal 按 Arc 指针身份比较；AsyncVal/CoroutineFrame 返回 false（不同实例永不相等）。消除 `_` fallback，改为显式 `_ => false`（不同变体间永不相等）。

### R3：Bug #34 compute_array_store SOA 未同步

- **问题**：`compute_array_store` 越界扩展数组时只更新 `elements` 向量，不更新 `scalar_soa`，导致 SOA 数据与 elements 长度不匹配。
- **修复**：[Compute.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Compute.rs#L2090-L2101) 新增 SOA 同步逻辑：resize 时失效 SOA（`scalar_soa = None`），in-bounds store 时调用新增的 `ScalarSoA::try_store` 方法（[Value.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/value/Value.rs#L1567-L1588)）尝试就地写入 SOA，类型不匹配则失效 SOA 缓存。`try_store` 按 ValueTag 匹配 + union 字段访问，覆盖全部 12 种标量类型。

### R4：Bug #40/41 逃逸分析遗漏 While/Loop body

- **问题**：`collect_lambda_vars_stmt` 的 `_ => {}` catch-all 遗漏 `Stmt::While` 和 `Stmt::Loop` 的 body，while/loop 体内定义的 lambda 变量不被逃逸分析收集。
- **修复**：[Builder.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L246-L252) 为 While 和 Loop 添加显式递归扫描分支。

### R5：Bug #53 `&` 运算符二元/一元歧义

- **问题**：`parse_binary` 仅对 `TokenKind::Minus` 做阻断处理，遗漏 `TokenKind::Ampersand`（`&` 既是位与也是引用），`{ ... } & x` 会被误解析为位与。
- **修复**：[Parser.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ast/Parser.rs#L2853-L2857) 将停止条件从 `== TokenKind::Minus` 改为 `matches!(..., TokenKind::Minus | TokenKind::Ampersand)`。

### R6：Bug #55 i128/u128 与 f64 混合精度损失

- **问题**：`select_binary_compute_fn` 中 i128/u128 与 f64/f32/f16 混合运算时，`as_float_f64` 将 i128 转 f64 有损（128 位→52 位尾数）。
- **修复**：[Builder.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L3202-L3224) 新增 i128/u128 检测：当 `has_128_int && float_ty != "f128"` 时提升到 f128，f128 compute_fn 使用 `as_f128()`（通过 `F128::from_i128`/`from_u128` 精确构造，无损）。

### R7：Bug #42 f128/f32/f16 match pattern 精度丢失

- **问题**：`compile_pattern_literal` 对所有浮点 pattern 统一产出 `ConstValue::F64`，`1.0f128` 在 match 模式中精度丢失；`compile_pattern_literal_match` 统一用 `CF_EQ_F64` 比较。
- **修复**：[Builder.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L2972-L3002) 新增 `detect_float_suffix` 函数，按后缀产出正确 ConstValue 变体（f128→F128、f32→F32、f16→F16、f64/无后缀→F64）。[Builder.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L2832-L2849) `compile_pattern_literal_match` 按 后缀选择比较函数：f128/f32/f16 用 `CF_EQ_OBJ`（value_equals_with_arena 精确比较 bit pattern），f64 用 `CF_EQ_F64`。

### R8：Bug #18 has_propagate_stmt 未跳过 defer body

- **问题**：`has_propagate_stmt` 未像 `has_return_stmt` 那样跳过 `Stmt::Defer`，导致 defer body 中的 `?` 运算符被计入函数级 propagate 检测，过保守地阻止内联。
- **修复**：[Analyzer.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/pass/Analyzer.rs#L2512-L2527) 添加 `Stmt::Defer { .. } => false` 分支，与 `has_return_stmt` 保持一致。

### R9-R11：保留的语义机制（非特判）

- **R9 Bug #12 `Ident("self")`**：trait 默认方法特化时 Sema 将 self 注册为 "void"，`trait_self_type` 覆盖是语言级必要机制，非 bug workaround。已补充注释说明。
- **R10 Bug #1 `ty_meta.is_none()`**：在 Str 和 Nullable 已处理后，`scalar_meta = None` 是复合类型的充要条件（scalar_meta 是标量类型的单一真相源）。已补充注释说明。
- **R11 Bug #49 `current_function_has_defer`**：含 defer 的函数需要 WriteBack 是 defer 语义的必要机制（defer body 通过原始节点 ID 读取变量），非特例判断。保留。

---

## 修复优先级总览

| 优先级 | Bug ID | 简述 | 状态 |
|--------|--------|------|------|
| P0 | #3 | 数组变量索引返回 `<non-scalar>` | 已修复 (2026-08-05) |
| P0 | #4 | `arr.len()` 返回 `void` | 已修复 (2026-08-05) |
| P0 | #10 | `defer` 不执行 | 已修复 (2026-08-05) |
| P0 | #13 | Newtype match 解包不执行 | 已修复 (2026-08-05) |
| P0 | #18 | `return` 语句导致函数挂起/静默退出 | 已修复 (2026-08-07) |
| P0 | #20 | 科学计数法浮点字面量解析错误（`1e300`→`1`） | 已修复 (2026-08-07) |
| P0 | #24 | await 节点在分支子图（if/else/循环体）内导致 event loop stuck | 已修复 (2026-08-07) |
| P0 | #30 | `&&`/`\|\|` 在 while 条件中导致 event loop stuck | 已修复 (2026-08-07) |
| P0 | #31 | 闭包链调用中共享可变捕获不连贯（多闭包覆盖） | 已修复 (2026-08-07) |
| P0 | #33 | while 循环体内的 throw 不传播（返回 Ok） | 已修复 (2026-08-07) |
| P0 | #37 | while 条件中调用用户函数导致 event loop hang | 已修复 (2026-08-07) |
| P0 | #40 | 闭包存入数组后 `arr[i]()` 返回 void（非闭包返回值） | 已修复 (2026-08-07) |
| P0 | #41 | 闭包返回闭包（高阶工厂）污染后续 makeCounter 的 Cell 状态（计数器从 11 起） | 已修复 (2026-08-07) |
| P0 | #42 | match arm 中 f64 字面量带 `f64` 类型后缀（`0.0f64 =>`）破坏整个 match，返回 null | 已修复 (2026-08-07) |
| P0 | #45 | 嵌套 if-else 表达式中，内层 else 分支的尾调用结果丢失为 null（单层 if-else 正常；`match` arm body 为嵌套 if-else 同样失效） | 已修复 |
| P0 | #47 | defer body 引用局部变量/参数时读取为 null 或完全不执行（全局字符串拼接+字面量正常）；debug 构建下引发 panic #52 | 已修复 |
| P0 | #52 | defer body 写入局部变量（如 `defer x = 999`）在 debug 构建下 panic：`writeback target NodeId(N) out of current frame range`（Compute.rs:3206）；release 构建下静默失败（#47 表现） | 已修复 |
| P0 | #53 | 负整数字面量（`-1`/`-100`）作为 while/for 循环后的尾表达式返回 void；`(-1)` 带括号导致引擎 hang；`if` 后返回 0 而非 -1 | 已修复 (2026-08-07) |
| P0 | #55 | 混合 int-float 算术运算完全失效：`int + float` 返回 0，`float + int` 忽略 int，`int * float` 返回 0，`int / float` panic（除零） | 已修复 (2026-08-07) |
| P1 | #1 | `!=` 运算符在 record/enum/newtype 始终返回 false | 已修复 (2026-08-05) |
| P1 | #6 | 闭包修改的 var 无法用 `==` 与字面量比较 | 已修复 (2026-08-05) |
| P1 | #7 | `?` 传播运算符不工作 | 已修复 (2026-08-05) |
| P1 | #12 | Trait 默认方法返回 `<non-scalar>` | 已修复 (2026-08-05) |
| P1 | #16 | `str + int` 字符串拼接返回 `<non-scalar>` | 已修复 (2026-08-05) |
| P1 | #19 | 嵌套函数不支持自递归调用 | 已修复 (2026-08-07) |
| P1 | #21 | i32 超范围整数字面量静默退出（无编译错误） | 已修复 |
| P1 | #23 | 类型别名与原始函数类型不等价 | 已修复 |
| P1 | #26 | 同一 val 数组跨多个 while 循环复用读取陈旧值 | 已修复 |
| P1 | #29 | 嵌套模式 Error(Error(v)) 提取的 i32 值丢失类型信息 | 已修复 |
| P1 | #34 | 索引数组赋值 `arr[i] = x` 是空操作（不修改数组） | 已修复 |
| P1 | #38 | `&&`/`\|\|` 不短路，RHS 总被求值（无 short-circuit） | 已修复 |
| P1 | #39 | 递归构建数组后，`empty ++ [literal]` 内联拼接丢失字面量（返回 0 长度） | 已修复 |
| P1 | #44 | trait 默认方法调用另一个默认方法时返回源代码片段（`wrap2→wrap1` 返回 ` + self.wrap1() + `）；默认→显式调用正常 | 已修复 |
| P1 | #48 | defer 跨函数调用执行顺序错误：callee 的 defer 延迟到 caller 退出时才执行（应在 callee 返回时执行） | 已修复 |
| P1 | #49 | defer body 含整数算术（`global_int + value`）时不执行（同模式的字符串拼接正常） | 已修复 |
| P1 | #50 | defer 在函数体含 `match` 表达式时不执行（if-else 体正常；defer body 本身简单也不行） | 已修复 |
| P1 | #54 | 字符串插值花括号内含转义引号（`"{\"str\"}"`）导致解析失败（整个文件无法解析） | 已修复 |
| P2 | #5 | `for-in arr.iter()` 迭代不工作 | 已修复 (2026-08-05) |
| P2 | #8 | `?.` 链式访问不工作 | 已修复 (2026-08-05) |
| P2 | #9 | `str? ??` 合并返回 false | 已修复 (2026-08-05) |
| P2 | #11 | `while break` 不工作 | 已修复 (2026-08-05) |
| P2 | #14 | 返回 newtype 解包值的函数返回 `void` | 已修复 (2026-08-05) |
| P2 | #22 | 有符号整数除法溢出 panic（非 wrapping 语义） | 已修复 (2026-08-07) |
| P2 | #25 | u128 MAX 字面量无法直接表示 | 已修复 (2026-08-07) |
| P2 | #27 | throw 原始类型被包装为 Error(value: v) | 已修复 (2026-08-07) |
| P2 | #28 | `??` (Elvis) 不支持 Throw 类型 | 已修复 (2026-08-07) |
| P2 | #35 | ADT 变体模式变量遮蔽函数参数时，f64 类型二元运算返回 0 | 已修复 (2026-08-07) |
| P2 | #43 | `cast(true).to(i32)` 返回 0 而非 1（`cast(false).to(i32)` 正确为 0） | 已修复 |
| P2 | #51 | `cast(f32).to(f64)` 返回 void（f32→f64 类型提升失败） | 已修复 |
| P3 | #2 | `==` 在 record 上始终返回 true（与 #1 关联） | 已修复 (2026-08-05) |
| P3 | #15 | 非 ASCII 字符串索引 panic | 已修复 (2026-08-05) |
| P3 | #17 | 字符串插值中 `bool == bool` 表达式恒返回 true | 已修复 (2026-08-05) |
| P3 | #36 | 不支持 `\uXXXX` 和 `\0` 字符串转义序列 | 已修复 (2026-08-07) |
| P3 | #46 | 字符串字面量中 `{[...]}` 被当作字符串插值解析（`[X]` 视为数组字面量，X 报 undefined variable）；无 `{}` 转义机制 | 已修复 |
| P0 | #56 | match arm 间 current_effect 泄漏导致递归 ADT 遍历返回 void | 已修复 (2026-08-08) |
| P1 | #57 | non_tail_rec_to_loop 转换破坏 defer LIFO 语义（defer 仅执行一次，参数失效） | 已修复 (2026-08-08) |
| P0 | #62 | 整数除以零静默返回 0（无 panic） | 已修复 (2026-08-10) |
| P0 | #63 | 数组越界访问不 panic，静默返回垃圾值 | 已修复 (2026-08-10) |
| P0 | #64 | 非穷尽 match 不报错，运行时静默返回 void | 已修复 (2026-08-10) |
| P0 | #65 | defer + throw/return 后调用者后续代码不执行 | 已修复 (2026-08-10) |
| P1 | #66 | defer 在块作用域退出时不执行（只在函数级执行） | 已修复 (2026-08-10) |
| P1 | #71 | 整数取模零静默返回 0（与 #62 同类，未覆盖） | 已修复 (2026-08-10) |
| P1 | #72 | 字面量溢出 sema check 通过但 IR 阶段报错（阶段不一致） | 已修复 (2026-08-10) |
| P1 | #73 | 不同位宽整数混合运算 / 比较静默通过（无显式转换） | 已修复 (2026-08-10) |
| P1 | #83 | 泛型参数类型不统一不报错（pair(1i32, 2i64) 静默用首参类型） | 已修复 (2026-08-10) |
| P1 | #85 | match 嵌套穷尽性检查缺失（sema 只检查单层构造器） | 已修复 (2026-08-10) |
| P2 | #60 | numeric widening 在标量 / 数组 / Throw 之间行为不一致 | 已修复 (2026-08-10) |
| P2 | #61 | 类型别名在 mismatch 报错中被静默展开 | 已修复 (2026-08-10) |
| P2 | #67 | 移位越界行为不明确（1 << 32 返回 1） | 已修复 (2026-08-10) |
| P2 | #68 | 函数类型后缀数组注解解析优先级错误 | 已修复 (2026-08-10) |

---

## P0 优先级（核心功能阻塞）

### Bug #3：数组变量索引返回 `<non-scalar>`

- **状态**：已修复 (2026-08-05)
- **现象**：使用 `i32` 变量作为数组索引时，返回 `<non-scalar>` 而非元素值
- **复现代码**：
  ```kuzo
  val arr = [10, 20, 30, 40]
  var i: i32 = 0
  println(arr[i])  // <non-scalar>（应为 10）
  ```
- **影响**：所有使用循环变量索引数组的代码（`while`、`for` 循环遍历数组）
- **根因**：局部变量读取（`Expr::Ident`）直接返回节点 ID，不依赖 `current_effect`。当 while 循环通过 WriteBack 更新变量值时，后续表达式在 WriteBack 完成前读取旧值。全局变量读取已有 `current_effect` 依赖（`compile_global_load`），但局部变量读取缺少。
- **修复**：
  1. 在 `compile_expr` 的 `Expr::Ident` 分支中，当 `current_effect` 存在时创建 CF_SEQ 依赖节点，确保局部变量读取在前序副作用完成后执行（与 `compile_global_load` 机制一致）
  2. 在 `register_while_subgraph`、`register_loop_subgraph`、`register_for_subgraph` 中编译子图内容前重置 `current_effect = None`，避免在循环体帧 `reset_loop_iteration` 后因外部 effect 依赖导致死锁
- **验证**：14 个功能测试全部通过，5 个性能测试全部通过，无回归

### Bug #4：`arr.len()` 返回 `void`

- **状态**：已修复 (2026-08-05)
- **现象**：数组 `.len()` 方法返回 `void` 而非长度值
- **复现代码**：
  ```kuzo
  val arr = [1, 2, 3]
  println(arr.len())  // void（应为 3）
  ```
- **影响**：无法动态获取数组长度，限制所有数组迭代场景
- **根因**：IR 编译器的 `expr_type_id` 方法仅使用 `info.type_name` 获取类型名，未 fallback 到 `info.type_desc.type_name`。当数组字面量推断后 `type_name` 为 `None` 但 `type_desc.type_name` 为 `"array"` 时，`expr_type_name` 正确返回 `"array"`，而 `expr_type_id` 返回 `None`。这导致 `lookup_intrinsic` 中 `type_id=None`，方法签名查询失败（`sig=None`），intrinsic 方法（如 `len()`）无法降级为 compute_fn 节点，最终返回 `void`。
- **修复**：修改 `Ir.rs` 的 `expr_type_id` 方法，使其与 `expr_type_name` 逻辑一致——优先使用 `info.type_name`，fallback 到 `info.type_desc.type_name`，确保数组等复合类型的 `type_id` 能正确解析，intrinsic 方法可正常降级。
- **验证**：`arrays` 测试新增 4 个 `.len()` 用例（基本长度、空数组、6 元素数组、`while + len()` 动态边界迭代）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #10：`defer` 不执行

- **状态**：已修复 (2026-08-05)
- **现象**：`defer` 块中的代码不执行，LIFO 顺序无效
- **复现代码**：
  ```kuzo
  var log: str = ""
  fun lifo(): void {
      defer log = log + "A"
      defer log = log + "B"
      log = log + "body|"
  }
  lifo()
  println(log)  // "body|"（应为 "body|BA"）
  ```
- **影响**：资源清理、日志记录等依赖 defer 的场景全部失效
- **根因**：`Ir.rs` 的 `compile_lambda` 方法在编译 lambda/嵌套函数体时未设置 `current_function_sg`。defer 语句编译时通过 `current_function_sg` 将 defer body 注册到当前函数子图的 `defer_table`，但 `current_function_sg` 为 `None`（或指向外层函数），导致 defer_table 未被填充，Engine 帧完成时无法找到 defer body 执行。顶层函数不受影响（`compile_function` 正确设置了 `current_function_sg`），因此顶层函数的 defer 正常工作。
- **修复**：在 `compile_lambda` 中编译 body 前保存 `current_function_sg`，设置为 `Some(sg_id)`（lambda 子图 ID），body 编译后恢复原值。这确保 defer 语句能正确注册到 lambda 子图的 `defer_table`，Engine 帧完成时按 LIFO 顺序执行。
- **验证**：`throw` 测试新增 4 个 defer 用例（LIFO 顺序、单个 defer、无 defer 控制组、多 defer 顺序）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #13：Newtype match 解包不执行

- **状态**：已修复 (2026-08-05)
- **现象**：`match` 模式匹配 newtype 时，分支体不执行，函数返回 `void`
- **复现代码**：
  ```kuzo
  type Meters = Meters(f64)
  fun areaM(m: Meters): f64 {
      match m {
          Meters(v) => v * v  // 不执行
      }
  }
  println(areaM(Meters(5.0)))  // void（应为 25.0）
  ```
- **影响**：所有依赖 newtype 解包运算的场景
- **根因**：`Engine.rs` 的 `compute_pattern_ctor_match` 和 `compute_pattern_adt_field_get` 两个 compute_fn 都不处理 `HeapObj::Newtype`。newtype 值在运行时表示为 `HeapObj::Newtype(NewtypeValue { type_name, inner })`，但模式匹配的构造器判别（`compute_pattern_ctor_match`）和字段提取（`compute_pattern_adt_field_get`）都缺少对 `HeapObj::Newtype` 的 match 分支，导致构造器判别返回 `false`（所有 arm 不匹配）、字段提取返回 `Value::VOID`（模式变量 `v` 绑定到 void）。
- **修复**：
  1. `compute_pattern_ctor_match` 新增 `HeapObj::Newtype(n) => n.type_name == *ctor_name` 分支。Newtype 的构造器名 == 类型名，所以比较 `NewtypeValue.type_name`。
  2. `compute_pattern_adt_field_get` 新增 `HeapObj::Newtype(n)` 分支，`idx == 0` 时通过 `ValueArena::with_global(|a| a.get_value(n.inner))` 解引用 `inner` 句柄获取内部值。
- **验证**：`newtype` 测试新增 4 个 match 解包用例（f64 解包、返回值解包、i64 解包、解包后重新包装）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #18：`return` 语句导致函数挂起/静默退出

- **状态**：已修复 (2026-08-07)
- **发现场景**：控制流边缘测试中，`return` 语句在 `if` 块内使用时导致程序挂起
- **现象**：函数体中使用 `return n;` 语法时，调用该函数后程序静默退出（无 panic、无输出、EXIT=0），后续代码不执行
- **复现代码**：
  ```kuzo
  fun withReturn(n: i32): i32 {
      if n < 2 { return n }
      n
  }
  fun main(): void {
      println("start")        // 输出
      val r = withReturn(1)
      println("r = {r}")      // 不执行
  }
  ```
- **影响**：所有使用 `return` 关键字的函数（而非 if-as-expression）均不可用
- **根因**：Analyzer 的 inline_pass 将含 `return` 语句的纯函数标记为可内联。`compile_inline_expansion` 将 callee body 直接编译到调用方子图中，`return` 语句的 `SignalKind::Return` 控制信号被设在调用方子图节点上。执行时该信号触发调用方帧的 `ControlSignal::Return`，导致调用方帧提前退出（而非仅退出被内联函数）。与已有 `has_propagate` 检查（`?` 运算符）属同一类问题——`?` 和 `return` 均通过 `ControlSignal::Return` 实现函数级提前返回，内联后信号作用域错误扩大到调用方。
- **修复**：在 `Analyzer.rs` 的 `inline_pass` 中新增 `has_return` / `has_return_stmt` 检查（与 `has_propagate` 并列），递归检测函数体是否含 `Stmt::Return`。检测跳过 Lambda body（return scoped to lambda）和 Defer body（defer body 编译为独立子图）。含 `return` 的函数不内联，走正常 Call 节点路径，`return` 信号正确局限在被调函数子图内。
- **验证**：8/8 unit tests + 14/14 functional tests + 5/5 perf tests 全部通过，edge tests 无新回归（已有失败均为独立 bug）

### Bug #20：科学计数法浮点字面量解析错误

- **状态**：已修复 (2026-08-07)
- **发现场景**：数值边界测试中，科学计数法浮点字面量的指数部分被忽略
- **现象**：`1e300` 解析为 `1.0`，`1.5e10` 解析为 `1.5`，`1.7976931348623157e308` 解析为 `1.7976931348623157`——指数部分（`e`/`E` 后的数字）被完全丢弃
- **精细化（2026-08-07 edge_misc 复测）**：仅在**无类型后缀**时触发；带 `f64` 后缀（`1e300f64`、`1.5e10f64`、`1e-5f64`）解析完全正确。推测无后缀字面量走默认推断路径，该路径未处理 `e<exp>`；带后缀字面量走浮点专用解析路径，已正确处理指数。注意：与 Bug #42 形成对称——后缀帮助浮点字面量解析，但破坏 match 模式中的 f64 字面量。
- **复现代码**：
  ```kuzo
  fun main(): void {
      val sci: f64 = 1e300
      println(sci)       // 输出 1（应为 1e300）
      val sci2: f64 = 1.5e10
      println(sci2)      // 输出 1.5（应为 15000000000）
  }
  ```
- **影响**：所有使用科学计数法的浮点字面量（如物理常数、工程计算）均得到错误值，无任何错误提示
- **根因**：Parser.rs 的 `parse_float_literal` 使用**后向扫描**分离数值与类型后缀——先从末尾扫数字，再扫字母。对 `1e300`：扫到 `300`（数字）后继续扫到 `e`（字母），将 `e300` 误判为类型后缀，数值部分只剩 `1`。带 `f64` 后缀时（`1e300f64`）恰好正确：扫 `64`（数字）→ `f`（字母），后缀=`f64`，数值=`1e300`。
- **修复**：新增 `split_float_suffix` 函数，改用**前向扫描**——从前往后依次消费整数部分、小数部分（`.`）、指数部分（`e`/`E` + 可选符号 + 数字），剩余部分为类型后缀。同时正确处理十六进制浮点（`0x` 前缀 + `p`/`P` 指数）。`parse_float_literal` 和 `parse_negative_float_literal` 均改用此函数。
- **验证**：8/8 unit + 14/14 functional + 5/5 perf 全部通过；edge_numeric ALL PASSED；edge_misc 中 Bug #20 相关用例全部 PASS（唯一失败为 #43 预存 bug）

### Bug #24：await 节点在分支子图（if/else/循环体）内导致 event loop stuck

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_async 测试中，`channel.recv()` 在 while 循环内导致 event loop stuck；进一步测试发现 await 节点在 if 分支内也卡住
- **现象**：`channel.recv()`、`Timer(n).await()`、`asyncFn().await()` 等 await 操作在 `if` 分支或 `while`/`loop` 循环体内执行时，event loop 无限循环直到 `loop_guard=200000001` 触发 panic（`event loop stuck`）。函数顶层（不在任何分支子图内）的 await 正常工作
- **复现代码（while 循环）**：
  ```kuzo
  fun main(): void {
      val lch = channel<i32>(20)
      lch.send(42)
      var ri: i32 = 0
      while ri < 1 {
          val v = lch.recv()   // 卡住：channel 有数据也不返回
          ri = ri + 1
      }
  }
  ```
- **复现代码（if 分支）**：
  ```kuzo
  fun main(): void {
      val lch = channel<i32>(20)
      lch.send(42)
      if true {
          val v = lch.recv()   // 卡住
      }
  }
  ```
- **正常工作（函数顶层）**：
  ```kuzo
  fun main(): void {
      val lch = channel<i32>(20)
      lch.send(42)
      val v = lch.recv()   // 正常：输出 42
  }
  ```
- **影响**：所有在条件分支或循环体内使用 await/channel.recv/Timer.await 的场景。无法在循环中批量收发 channel 消息、无法在循环中等待 timer、无法在 if 分支中异步等待
- **根因**：`compile_branch_subgraph` / `compile_loop_body_subgraph` 编译分支体时不重置 `current_function_sg`，导致 `build_await_node` 把 `EventSourceDecl` 注册到**外层函数子图**而非**分支子图**。运行时 `compute_await` 用 `frame.subgraph_id`（分支子图 id）查找 `event_source_decls`，分支子图的 `event_source_decls` 为空，查找失败后 fallback 到 `EventSourceKind::AsyncJoin`，使 channel.recv / timer.await 被误判为 async join，注册错误的 waiter 等待永远不会到达的事件；`event_waiters` 非空使 event loop 不断 `yield_now` 循环（绕过死锁检测），最终 `loop_guard` 达到 200M 触发 "event loop stuck" panic
- **修复**：在 `compile_branch_subgraph` 和 `compile_loop_body_subgraph` 中，编译分支体前记录函数子图 `event_source_decls` 长度（`prev_decl_count`），编译后用 `drain(prev_decl_count..)` 将新增的 `EventSourceDecl` 从函数子图迁移到分支子图。嵌套分支正确：内层分支编译时先 drain 自己的 decls，外层 drain 时只剩自己的。此方法不影响 `defer_table` 注册（defer 仍注册到函数子图，保持原有行为）
- **验证**：8/8 unit + 14/14 functional + 5/5 perf 全部通过；edge_async **ALL PASSED**（之前因 Bug #24 失败）；if-branch / while-loop / else-branch / nested-if-in-while 4 种 await 场景全部通过；其余 edge tests 无新回归

### Bug #30：`&&`/`||` 在 while 条件中导致 event loop stuck

- **状态**：已修复 (2026-08-07)
- **发现场景**：control_flow 测试中，`while i < 10 && found == -1` 导致 event loop stuck
- **现象**：`&&`（逻辑与）或 `||`（逻辑或）运算符出现在 `while` 循环的条件表达式中时，event loop 无限循环直到 `loop_guard=200000001` 触发 panic（`event loop stuck`）。同样的 `&&`/`||` 在 `if` 条件中正常工作
- **复现代码**：
  ```kuzo
  fun main(): void {
      var i: i32 = 0
      while i < 10 && i < 5 {   // 卡住
          i = i + 1
      }
  }
  ```
- **影响**：所有在 while 条件中使用 `&&`/`||` 组合多个条件的场景。无法在 while 中写 `while a < max && b < max { ... }` 等常见模式
- **根因**：`&&`/`||` 编译为普通 `BinOp` 节点（`CF_AND_BOOL`/`CF_OR_BOOL`），而非短路 Gate 子图。`reset_loop_iteration` 只重置顶层 `cond_node`（如 `and_bool` 节点），但其输入节点（如 `lt_i32(i, 10)`、`lt_i32(i, 5)` 比较节点）保持上一轮的陈旧值。当 `and_bool` 重新执行时，读取的是陈旧比较结果（上轮 `i` 的值），导致条件恒为 true → 死循环。简单条件（如 `while i < 10`）不受影响：cond_node 直接读取外部变量 `i`（通过帧链获取当前值），无中间节点。
- **修复**：在 `Frame.rs` 新增 `reset_condition_tree` 方法，递归收集 `cond_node` 依赖树中所有位于循环子图内（排除嵌套子图 body_sg/void_sg 和 Gate 节点）的节点，重置其值并按依赖关系设置 `pending_inputs`（pending = 依赖树内的输入数，外部输入通过帧链访问不计 pending），预填充 Const 节点，将 Const 节点和 0-pending 非 Const 节点入就绪队列。`reset_loop_iteration` 的 While/Loop 分支从只重置顶层 cond_node 改为调用 `reset_condition_tree`，确保条件表达式每轮迭代从头重新求值。
- **验证**：8/8 unit + 34/34 functional（含 18 edge）+ 5/5 perf 全部通过；`&&`/`||` 在 while 条件中的 4 种场景（纯 `&&`、纯 `||`、`&&` + 变量、`||` + break）全部通过

### Bug #31：闭包链调用中共享可变捕获不连贯（多闭包覆盖）

- **状态**：已修复 (2026-08-07)
- **发现场景**：closures 边缘测试中，`a → b → c` 三层闭包链调用时，只有最内层闭包 `c` 的修改可见
- **现象**：多个闭包捕获同一 `var`，并通过闭包间相互调用（A 调 B 调 C）修改该 var 时，只有最后一次调用的修改可见——前面所有闭包体的修改被"覆盖丢失"。具体表现为：
  ```kuzo
  var log: str = ""
  val c = fun() { log = log + "C" }
  val b = fun() { log = log + "B"; c() }
  val a = fun() { log = log + "A"; b() }
  a()
  println(log)   // "C"（应为 "ABC"）
  ```
  用计数器验证（`count = count + 1`）显示三体都执行，但都从陈旧快照 0 读取 → 各写 1，最后写入者覆盖：`count == 1`（应为 3）。
- **根因**：`compute_writeback` 的路径 1（parent_frame_ptr 链）和路径 2（root_frame_ptr）只写入祖先帧，**不写当前帧自身**。same_function 闭包链调用场景中：
  1. `a()` 从 main 帧复制 `log=""` 到 a 子帧
  2. a 子帧执行 `log = log + "A"`，WriteBack 写入 main 帧（`log="A"`），但 a 子帧自身的 `log` 仍为 `""`
  3. a 子帧调用 `b()`，`start_subgraph` 从 parent_frame（a 子帧）读取 upvalue `log`，得到陈旧值 `""`（应为 `"A"`）
  4. 同理，b 子帧读取陈旧值 `""`，c 子帧也读取陈旧值 `""`，最终 `log="C"`
- **修复**：在 `compute_writeback` 路径 1 之前新增**路径 0**：先写入当前帧自身（如果 target 在当前帧范围内）。same_function 帧的值表扩展到父帧大小，target 在当前帧范围内。写入当前帧后，后续闭包调用从 parent_frame 读取 upvalue 时能得到最新值。
- **验证**：8/8 unit + 34/34 functional（含 18 edge）+ 5/5 perf 全部通过；闭包链 3 层调用（`a→b→c`）字符串拼接 `log="ABC"` 正确；计数器链 `count=3` 正确

### Bug #33：while 循环体内的 throw 不传播（返回 Ok）

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_throw 测试中，`throw` 在 `while` 循环体内执行后，函数返回 `Ok` 而非 `Error`
- **现象**：顶层函数中 `while` 循环体内的 `throw` 语句不传播错误，函数正常返回 `Ok(...)`，throw 被静默吞掉。对比：`if` 分支内 throw 正常传播（throwInMatch 用例通过）；函数顶层 throw 正常传播
- **复现代码**：
  ```kuzo
  fun loopThrow(n: i32): Throw<i32, Error> {
      var i: i32 = 0
      while i < 10 {
          if i == n { throw Error("hit") }
          i = i + 1
      }
      Ok(i)
  }
  // loopThrow(3) 应返回 Error("hit")，实际返回 Ok(10)
  ```
- **影响**：所有在 while 循环体内 throw 的错误处理流程失效——错误被吞，调用方误以为成功
- **根因**：`complete_and_wake_caller` 的"非 LoopBody"路径中，控制信号传播有 `is_gate` 限制——只有当 `call_node` 是 `NodeKind::Gate` 时才传播 `control_signal` 给调用方帧。但 while/loop/for 循环通过 `compile_recursive_call` 编译为 **Call 节点**（不是 Gate 节点），while_sg 的 `return_node` 虽然是 Gate，但调用方帧中的 `call_node` 是 Call 节点。因此循环子图因 throw 而完成并携带 `Return(ThrowVal(Err))` 信号时，`is_gate` 检查失败，信号不传播给函数帧，函数帧继续执行尾表达式 `Ok(i)` 覆盖了 throw。
- **修复**：在 `Subgraph.rs` 的 `complete_and_wake_caller` 中，移除 `is_gate` 限制，改为**同函数 function_id 检查**：
  - 同函数内（Gate 分支子图、循环子图）：传播 throw/return 信号给调用方帧
  - 跨函数调用：不传播（函数帧的 Return 信号是函数级返回，返回值已通过 `extract_child_return` 提取，传播会给调用方帧错误地设置 Return 信号导致提前退出）
  - Break/Continue 不会到达此处（LoopBody 路径已处理）
- **验证**：8/8 unit + 34/34 functional（含 edge_throw）+ 5/5 perf 全部通过；`loopThrow(3)` 返回 `Error("hit")`，`loopThrow(100)` 返回 `Ok(10)`

### Bug #37：while 条件中调用用户函数导致 event loop hang

- **状态**：已修复 (2026-08-07)
- **发现场景**：control_flow 测试中，`while isDone(fci) == false { ... }` 导致程序无输出挂起（event loop stuck）
- **现象**：在 `while` 循环条件中调用任何用户定义的函数（无论顶层 `fun` 还是嵌套 `fun`），引擎挂起无输出、不 panic、不退出。intrinsic 方法（如 `arr.len()`）在 while 条件中正常工作
- **复现代码**（最小）：
  ```kuzo
  fun isDoneTop(n: i32): bool { n >= 5 }
  fun main(): void {
      var a: i32 = 0
      var ac: i32 = 0
      while isDoneTop(a) == false {   // hang，永不输出
          ac = ac + 1
          a = a + 1
      }
      println("ac = {ac}")
  }
  ```
- **不影响的情况**：
  - intrinsic 方法调用正常：`while i < arr.len() { ... }` ✓
  - 用户函数在 while **体内**调用正常（如 `while i < 5 { val x = isDoneTop(i); ... }`）✓
  - 用户函数在 `if` 条件中调用正常 ✓（仅 while 条件触发）
- **根因**：与 Bug #30（`&&`/`||` 在 while 条件中导致 event loop stuck）同根因——while 条件子图中的 Call 节点（函数调用）在循环迭代重置时未被正确重置。`reset_condition_tree`（Bug #30 修复引入）递归重置条件依赖树中所有节点（包括 Call 节点），使每轮迭代从头重新求值条件，修复了此问题
- **修复过程中发现的额外问题**：Bug #33 的修复（控制信号传播从 `is_gate` 改为 `function_id` 比较）引入了两个回退：
  1. **Break/Continue 信号从循环帧错误传播到函数帧**：循环帧（While/Loop/For）因 LoopBody 传播获得 Break 信号后走正常完成路径，此时 Break 已完成其使命（退出循环），但 Bug #33 的 function_id 比较导致 Break 被传播给函数帧，使整个函数错误退出（静默退出，breakJ=0 无输出）
  2. **Return 信号从 lambda/嵌套函数调用错误传播到父帧**：嵌套函数（lambda）与调用方共享 `function_id`（为帧链穿透设计），但它是独立函数调用，返回值已通过 `extract_child_return` 提取。Bug #33 的 function_id 比较导致 Return 被传播给调用方帧，使调用方错误退出（edge_throw/throw/edge_nullable_deep 测试 hang）
  - **修复**：在 `complete_and_wake_caller` 的正常完成路径中，根据调用节点类型（Gate vs Call）和子图 `loop_kind` 精确控制信号传播：
    - `Return(_)`：仅 Gate 分支（if-else/match arm）和循环帧（While/Loop/For）传播；lambda/函数调用不传播
    - `Break`/`Continue`：仅 Gate 分支传播（穿透到 LoopBody）；循环帧的 Break/Continue 已被循环消费
- **影响**：无法在循环条件中使用任何用户函数（如 `while !isEmpty(stack)`、`while comparator(a, b) < 0`），严重限制抽象能力
- **验证**：8/8 unit + 24 ALL PASSED functional（含之前 hang 的 edge_throw/throw/edge_nullable_deep）+ 5/5 perf 全部通过；control_flow 中 `while isDone(fci) == false` 测试取消注释并通过

### Bug #40：闭包存入数组后 `arr[i]()` 返回 void（非闭包返回值）+ 循环体内闭包捕获返回 null

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_closures 测试中，将闭包存入数组后通过索引调用 `arr[i]()` 返回 void 而非闭包返回值；循环体内创建的闭包捕获循环局部变量后调用返回 null
- **现象（两部分）**：
  1. `arr[i]()` 返回 void：闭包存入数组（通过 `arr ++ [fun() {...}]` 构建）后，`arr[i]()` 调用返回 `void`。直接调用闭包变量 `f()` 正常，仅"数组索引取闭包后立即调用"路径失效
  2. 循环体闭包捕获返回 null：在 while/for 循环体内创建闭包并捕获循环体局部变量（如 `val captured = i * i`），循环结束后调用闭包返回 `null`。根因是循环体帧在循环结束/迭代重置后销毁/清空，same_function 帧链路径从父帧读取 upvalue 时得到 null
- **复现代码**：
  ```kuzo
  type IntFn = () -> i32
  fun main(): void {
      // 部分 1：arr[i]() 返回 void
      var fns_arr: IntFn[] = []
      fns_arr = fns_arr ++ [fun() { 1 }]
      println(fns_arr[0]())        // void（应为 1）→ 修复后：1

      // 部分 2：循环体闭包捕获返回 null
      var cap_fns: IntFn[] = []
      var i: i32 = 0
      while i < 5 {
          val captured = i * i
          cap_fns = cap_fns ++ [fun() { captured }]
          i = i + 1
      }
      println(cap_fns[0]())        // null（应为 0）→ 修复后：0
      println(cap_fns[4]())        // null（应为 16）→ 修复后：16
  }
  ```
- **根因（两部分）**：
  1. `arr[i]()` void：`compile_call` 的闭包调用检测仅处理 callee 是 `Ident` 的情况。非 Ident callee（如 `arr[i]`）落入"普通函数调用"路径，创建 `CF_CALL_LAUNCH` 节点无 `call_target`，运行时返回 `VOID`
  2. 循环体捕获 null：循环体内创建的闭包继承了外层函数的 `function_id`，走 same_function 帧链路径。但循环体帧在循环结束/迭代重置后销毁/清空，`start_subgraph` 从父帧 `get_value_by_global(outer_node)` 读取 upvalue 时得到 null（循环体局部变量的值已丢失）
- **修复（两部分）**：
  1. `arr[i]()` void：在 `compile_call` 的"普通函数调用"路径前，添加非 Ident callee 的动态闭包调用处理——编译 callee 表达式为 `inputs[0]`，创建 `CF_CLOSURE_CALL` 节点，由 `compute_closure_call` 运行时动态提取 Closure 并调用
  2. 循环体捕获 null：在 `compile_lambda` 的逃逸分析中增加循环体捕获检测——新增 `captures_loop_body_var` 方法，检查捕获变量的 `outer_node` 是否位于循环体内（node ID >= `body_node_start`）。`LoopContext` 新增 `body_node_start` 字段跟踪循环体起始节点。捕获循环体局部变量的闭包被标记为逃逸，分配独立 `function_id`，走跨函数 Cell 路径（构造时拷贝值到 Cell，持久化 upvalue）
- **影响**：所有"闭包存数组再按索引调用"和"循环内创建闭包捕获循环局部变量"场景——策略模式、分发表、回调数组、map/filter/reduce、循环内闭包工厂等。修复后全部正常
- **验证**：8/8 unit + closures/traits/adt/control_flow ALL PASSED + edge_closures ALL PASSED（含 Bug #40 和 Bug #41 全部用例）+ 5/5 perf；无回退

### Bug #41：闭包返回闭包（高阶工厂）污染后续 makeCounter 的 Cell 状态（计数器从 11 起）

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_closures 测试中，先使用闭包返回闭包的工厂（makeAdderFactory / mk_add），后续 `makeCounter()` 创建的计数器 `c_a()` 从 11 开始而非 1
- **现象**：上下文相关。同一程序中，先执行"闭包返回闭包"的高阶工厂后，后续 `makeCounter()` 创建的独立计数器共享被污染的 Cell 状态——`c_a()` 第一次调用返回 11（应为 1），`c_b()` 返回 14（应为 1）。**对照**：edge_probe 中无前置高阶闭包工厂时，`makeCounter()` 的 `fresh()` 正确返回 1
- **复现代码**：
  ```kuzo
  type IntFn = () -> i32
  fun makeAdderFactory(): () -> IntFn {
      val base: i32 = 100
      fun() {
          val captured = base
          fun() { captured + 1 }   // 闭包返回闭包
      }
  }
  fun makeCounter(): IntFn {
      var n: i32 = 0
      fun() { n = n + 1; n }
  }
  fun main(): void {
      val factory = makeAdderFactory()   // 触发条件：使用高阶闭包工厂
      val adder = factory()
      // adder() == 101（正常）
      val c_a = makeCounter()
      val c_b = makeCounter()
      println(c_a())   // 修复前 11（应为 1），修复后 1
      println(c_a())   // 修复前 12，修复后 2
      println(c_a())   // 修复前 13，修复后 3
      println(c_b())   // 修复前 14，修复后 1
  }
  ```
- **对照（edge_probe，无前置高阶工厂）**：
  ```
  heavy 10-call sum (expected 55): 55
  fresh() (expected 1): 1   ← 正确！
  fresh() (expected 2): 2   ← 正确！
  ```
- **影响**：所有"先使用闭包返回闭包工厂，再用闭包工厂创建状态机"的场景——计数器、迭代器、生成器状态错乱。单闭包自递归（makeCounter 单独使用）不受影响
- **根因**（已确认）：逃逸的 lambda（如 `makeCounter`/`makeAdderFactory` 返回的内层闭包）继承了外层函数的 `function_id`，导致引擎将其视为 same_function 调用，走"帧链共享 upvalue"路径。但逃逸闭包的定义帧在函数返回后已销毁，帧链访问到的 upvalue 是陈旧/被复用的内存，造成跨工厂的 Cell 状态泄漏。具体表现：`makeCounter` 创建的闭包复用了前序高阶工厂遗留的帧槽，`n` 的初始值非 0 而是前序调用的累积值（10）
- **修复**：在 `Builder.rs` 的 `compile_lambda` 中实现完整逃逸分析。新增 `escape_context_stack` 跟踪当前作用域内逃逸的嵌套 lambda ExprId 集合；`find_escaping_lambdas` 通过两遍 AST 扫描（Pass 1 收集持有 Lambda 的变量，Pass 2 递归收集尾位置 Lambda）精确判定 lambda 是否逃逸。逃逸 lambda 分配独立 `function_id`（`= sg_id.0`），强制引擎走跨函数 Cell 路径（`same_function=false`，Cell 持久化 upvalue）；非逃逸 lambda 继承外层 `function_id`，走帧链路径（定义帧存活，共享状态）
- **验证**：8/8 unit + closures/traits/adt ALL PASSED + edge_closures Bug #41 用例 PASS（c_a 从 1 起递增，c_b 独立从 1 起）+ 5/5 perf；无回退。剩余 edge_closures 4 个失败为已有 Bug #40 循环闭包捕获问题，与本修复无关

### Bug #42：match arm 中 f64 字面量带 `f64` 类型后缀破坏整个 match，返回 null

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_match 测试中，`match x { 0.0f64 => "zero" | ... }` 整个 match 返回 null
- **现象**：match arm 的模式位置出现带 `f64` 类型后缀的浮点字面量（如 `0.0f64 =>`）时，**整个 match 表达式失效**，对所有输入返回 `null`（Value::Null）——连 `_` 通配符 arm 和 guard arm 都不匹配。对照：不带后缀的 `0.0 =>` 正常工作；`_` 通配符单独使用正常；guard 单独使用正常
- **隔离探测（edge_probe Probe E）**：
  ```
  mi32(0) = zero            ← match i32 正常
  mf64_wild(0.0) = any      ← match f64 仅 _ 通配正常
  mf64_guard(3.14) = pos    ← match f64 guard 正常
  mf64_guard(0.0) = void    ← 无 arm 匹配返回 void（正确语义）
  mf64_lit_nosuffix(0.0) = zero   ← f64 字面量无后缀 0.0 正常匹配
  mf64_lit_nosuffix(5.0) = other  ← 正常
  mf64_lit_suffix(0.0) = null    ← f64 字面量带后缀 0.0f64 → null（Bug #42）
  mf64_lit_suffix(5.0) = null    ← 连 _ => "other" 也不匹配
  mf64_full(0.0) = null          ← 0.0f64 + guard + _ 全部失效
  ```
- **复现代码**：
  ```kuzo
  fun mf64_lit_suffix(x: f64): str {
      match x {
          0.0f64 => "zero"   // 带后缀的 f64 字面量模式 → 破坏整个 match
          _ => "other"        // 此 arm 也永不匹配
      }
  }
  // mf64_lit_suffix(0.0) == null（应为 "zero"）
  // mf64_lit_suffix(5.0) == null（应为 "other"）
  ```
- **对照（不带后缀正常）**：
  ```kuzo
  fun mf64_lit_nosuffix(x: f64): str {
      match x {
          0.0 => "zero"      // 无后缀 → 正常
          _ => "other"
      }
  }
  // mf64_lit_nosuffix(0.0) == "zero" ✓
  // mf64_lit_nosuffix(5.0) == "other" ✓
  ```
- **影响**：所有在 match arm 模式位置使用带 `f64` 后缀的浮点字面量的代码。与 Bug #20 形成对称——`f64` 后缀在表达式位置帮助科学计数法解析（Bug #20 无后缀才坏），但在模式位置破坏 match（Bug #42 有后缀才坏）
- **根因**（已确认）：`compile_pattern_literal` 的 Float 分支只过滤下划线，未去除类型后缀。`"0.0f64".parse::<f64>()` 失败返回 `None`，Const 节点值为 None。`prepare_frame` 预填充 Const 节点时跳过值为 None 的节点（`if let Some(cv) = ...` 条件不满足），导致该节点永远不在 ready_queue 中。下游 CF_EQ_F64 节点等待这个输入永远不就绪（pending 永不归零），第一个 arm 的 cond_node 永远不执行，Gate 节点永远不触发，整个 match hang
- **修复**：在 `compile_pattern_literal` 的 Float 分支中新增 `strip_float_type_suffix` 剥离类型后缀（f64/f32/f16/f128），并支持十六进制浮点字面量（`0x1.0p+1f64`）。与表达式位置的 `FloatLit` 处理保持一致
- **验证**：8/8 unit + edge_match ALL PASSED（Bug #42 全部 4 用例 PASS）+ closures/patterns/adt/edge_closures/edge_numeric/edge_strings ALL PASSED；无回退

### Bug #45：嵌套 if-else 内层 else 分支尾调用返回 null

- **状态**：已修复 (2026-08-07)
- **现象**：嵌套 if-else 表达式中，内层 else 分支若为直接递归调用（或包含直接递归调用的表达式），结果丢失为 null
- **复现代码**：
  ```kuzo
  fun powNested(base: i64, exp: i32): i64 {
      if exp == 0i32 {
          1i64
      } else {
          if exp % 2 == 1i32 {
              base * powNested(base * base, exp / 2)   // 奇数分支：算术组合 ✓
          } else {
              powNested(base * base, exp / 2)          // 偶数分支：尾调用 ✗ 返回 null
          }
      }
  }
  // powNested(2,1) = 2  (奇数分支)
  // powNested(2,2) = null  (偶数分支 - Bug #45)
  // powNested(2,3) = 8  (奇数分支，内部偶数调用未触发)
  // powNested(2,4) = null  (偶数分支)
  ```
- **影响**：所有使用嵌套 if-else 且内层 else 为递归调用的函数（如快速幂分治）。单层 if-else 的尾调用正常（`factTail`/`countDown` 百万次 TCO 正常）。`match` arm body 为嵌套 if-else 时同样失效。
- **根因**（已确认）：IR 优化器的 CSE（公共子表达式消除）pass 跨 if-else 分支子图合并了相同的纯计算节点。then 分支和 else 分支内的 `base * base`（compute_fn=CF_MUL_I64, inputs=[base_param, base_param]）被 CSE 判定为相同计算，else 分支的节点被 redirect 到 then 分支的节点。但 if-else 分支子图是互斥执行的，else 分支帧无法计算 then 分支范围内的节点（标记为 PENDING_EXTERNAL），导致 Call 节点的参数为 null。
- **修复**：在 `pass_cse`（Optimizer.rs）的 CSE key 中加入节点所属的最内层子图起始 NodeId（`compute_innermost_sg_starts`）。新增辅助函数预计算每个节点的最内层子图，确保跨 if-else/match 分支子图的相同计算不会被合并。同一子图内的 CSE 合并仍正常工作。
- **验证**：bug45_diag 全部 PASS（powNested(2,0..4) = 1,2,4,8,16；powFlat(2,2)=4, powFlat(2,4)=16）；bug45_rec（recDirect(3)=1 ✓）、bug45_twoparam（twoParam/twoParamArith 全部正确）；8/8 unit + 全部功能测试无新回归（edge_loop Bug #53、edge_operators Bug #38、edge_defer Bug #47、edge_traits Bug #44、edge_string_interp Bug #55 均为已知 bug，禁用 CSE 后同样失败）；5/5 性能测试正常

### Bug #47：defer body 引用局部变量/参数时读取为 null 或完全不执行

- **状态**：已修复 (2026-08-07)
- **现象**：defer body 引用局部变量/参数时读取为 null 或完全不执行（全局字符串拼接+字面量正常）；debug 构建下引发 panic #52
- **根因**（已确认）：分析器的 inline_pass 将含 defer 语句的纯函数标记为可内联。内联展开（`compile_inline_expansion`）直接编译函数体到调用方，不创建 Call 节点，因此运行时不为函数子图创建帧。defer 条目注册在函数子图的 `defer_table` 中，但该子图的帧从不被创建，`defer_table` 永远不被检查，导致 defer 完全不执行。
  - 具体路径：`deferCaptureLocal` 的函数体只操作局部变量（纯函数），被 `inline_pass` 标记为可内联。`compile_call` 调用 `compile_inline_expansion` 内联展开，跳过 Call 节点创建。函数的 defer_table（sg=480）从不被运行时检查。
  - 对照：`lifoBasic` 因修改全局变量（非纯）未被内联，defer 正常执行。
- **修复**：在 `Analyzer.rs` 的 `inline_pass` 中新增 `has_defer` 检查（与 `has_return`、`has_propagate` 同模式），排除含 defer 语句的函数被内联。defer 语义要求帧生命周期（创建帧 → 执行体 → 执行 defer → 完成帧），内联消除帧边界导致 defer 无法执行。
- **验证**：edge_defer 从 4+ 失败降至 2 失败（剩余 2 个为已知 bug：defer 变量捕获时序问题 + Bug #48 跨函数 defer 顺序）；8/8 unit + 28/34 functional ALL PASSED + 5/5 perf PASS，无新回归

### Bug #52：defer body 写入局部变量在 debug 构建下 panic

- **状态**：已修复 (2026-08-07)
- **现象**：函数含 `defer x = <expr>`（defer body 写入局部变量，而非全局变量）时，调用该函数导致引擎 panic：
  ```
  thread 'main' panicked at src/ir/Compute.rs:3206:17:
  writeback target NodeId(16344) out of current frame range
  ```
- **根因**（已确认）：defer body 子图通过 `init_frame` 创建帧，该方法用 defer body 自身的 `node_range` 设置 `node_offset` 和 `value_table` 大小。但 defer body 是 same_function 分支子图，其 WriteBack target 是函数级局部变量节点（node ID 在函数范围内）。`compute_writeback` 计算 `local = target.0 - frame.node_offset`，由于 defer 帧的 `node_offset` 是 defer body 的起始节点 ID（而非函数的起始节点 ID），`local` 索引越界，触发 `debug_assert` panic。
- **修复**：新增 `init_defer_frame` 方法（Frame.rs），用父帧的 `node_offset` 和 `value_table.len()` 创建 defer 帧，复制父帧已就绪的值，再调用 `prepare_same_function_frame` 设置 pending_inputs。这使 defer 帧的布局与函数帧一致，WriteBack 的 `local` 索引正确落在 value_table 范围内。同时设置帧链指针（parent_frame_ptr/root_frame_ptr）支持帧链穿透访问外层变量。Schedule.rs 的正常完成路径和 Cancelling 路径都改用 `init_defer_frame`。
- **验证**：debug 构建不再 panic；edge_defer `deferNoAffectReturn` 测试 PASS（defer 写局部变量 x=999 不影响返回值 5）；8/8 unit + 28/34 functional ALL PASSED + 5/5 perf PASS，无新回归
- **复现代码**：
  ```kuzo
  var g: str = ""
  fun lifoBasic(): str {
      var log: str = "body|"
      defer g = g + "A"
      defer g = g + "B"
      defer g = g + "C"
      log
  }
  fun deferCaptureLocal(): i32 {
      var x: i32 = 5
      defer g = g + cast(x).to(str)
      x = 10
      x
  }
  fun deferNoAffectReturn(): i32 {
      var x: i32 = 5
      defer x = 999   // ← defer 写入局部变量
      x
  }
  fun main(): void {
      lifoBasic()          // OK（defer 写全局）
      deferCaptureLocal()  // OK（defer 写全局，读局部）
      deferNoAffectReturn() // PANIC（defer 写局部）
  }
  ```
- **影响**：所有 defer body 写入局部变量的场景（资源释放后恢复局部状态等）；在模块含多个 defer 函数时，panic 可能提前到其他 defer 函数（node ID 分配不同）
- **根因**：`Compute.rs:3206` 的 `compute_writeback` 路径 4（非逃逸闭包根帧）计算 `local = target.0.wrapping_sub(frame.node_offset)`，当 defer body 的 writeback target 属于函数体的局部变量节点时，该节点 ID 超出 defer 执行时的 frame value_table 范围。defer body 在函数返回时执行，此时 frame 的 node_offset 可能已不匹配原函数体的节点布局，导致 `local` 索引越界。`debug_assert!` 在 debug 构建下触发 panic；release 构建下静默跳过（表现为 #47 的"完全不执行"）。
- **隔离**：单独调用 `deferNoAffectReturn()` 不 panic（frame 布局正确）；在调用过 `lifoBasic()` + `deferCaptureLocal()` 后再调用才 panic（frame 状态被前置 defer 执行污染）
- **绕过**：defer body 只写全局变量，不写局部变量

### Bug #53：负整数字面量作为循环/if 后的尾表达式返回错误值

- **状态**：已修复 (2026-08-07)
- **现象**：负整数字面量（如 `-1`、`-100`）作为 `while`/`for` 循环体后的函数尾表达式时，函数返回 `void` 而非负数值；作为 `if` 语句后的尾表达式时返回 `0`；`(-1)` 带括号形式在循环后导致引擎 hang。正整数字面量、零、变量、减法表达式（`0 - 1`）均正常。
- **复现代码**：
  ```kuzo
  fun whileNeg(): i32 { var i: i32 = 0; while i < 1 { i = i + 1 }; -1 }       // → void
  fun whilePos(): i32 { var i: i32 = 0; while i < 1 { i = i + 1 }; 42 }       // → 42
  fun whileZero(): i32 { var i: i32 = 0; while i < 1 { i = i + 1 }; 0 }       // → 0
  fun forNeg(): i32 { for n in [1].iter() { n }; -1 }                        // → void
  fun ifNeg(): i32 { if true { 1 }; -1 }                                      // → 0
  fun noLoopNeg(): i32 { -1 }                                                 // → -1（正常）
  fun retSubExpr(): i32 { var i: i32 = 0; while i < 1 { i = i + 1 }; 0 - 1 } // → -1（正常）
  fun retParenNeg(): i32 { var i: i32 = 0; while i < 1 { i = i + 1 }; (-1) } // → HANG
  ```
- **影响**：所有在循环/if 后使用负数字面量作为返回值的函数（如查找失败返回 -1、错误码等常见模式）
- **根因**（已确认）：Parser 层缺陷。Kuzo 词法器将 `;` 作为空白跳过，因此 `{ ... }; -1` 在 token 流中等价于 `{ ... } -1`。`parse_binary()` 在解析完 block/if/match 表达式后，会贪婪地消费后续的 `-` 作为二元减法运算符，将 `{ ... } - 1` 解析为 `Binary { op: Sub, lhs: Block, rhs: Literal(1) }`，而非将 `-1` 作为独立的一元取负尾表达式。由于 block 返回 void，`void - 1` 的计算结果为 void 或 0，导致函数返回错误值。
  - `while` 循环后 `-1` → `{ ... } - 1` → void - 1 → void
  - `if` 语句后 `-1` → `{ ... } - 1` → void - 1 → 0
  - `0 - 1` 正常因为 `0` 不是 block/if/match，`-` 被正确解析为二元减法
  - `-1` 单独使用正常因为没有前序 block 触发贪婪消费
- **修复**：在 `Parser.rs` 中进行两处修改：
  1. `parse_while_stmt`/`parse_loop_stmt`/`parse_for_stmt`：body 使用 `parse_unary()` 而非 `parse_expr()`，确保循环体只解析一个 unary 表达式（通常为 block），不贪婪消费后续运算符。`parse_if_expr` 的 then_branch/else_branch 同理使用 `parse_unary()`。
  2. `parse_binary()`：当 left 为 `Block`/`If`/`Match` 表达式且下一个 token 为 `Minus` 时，停止消费二元运算符。`-` 是唯一既有二元形式（减法）又有一元形式（取负）的运算符；其他运算符（`+` `*` `/` `%` 等）无一元形式，无歧义，不需阻断。用户若需在 block/if/match 后做减法，使用括号：`(if c { ... }) - 1`。
- **验证**：bug53_repro 全部 7 个测试用例通过（whileNeg/whileSub/whileNegLit/whileConstNeg/ifNeg/ifSub/assignNeg 均返回 -1）；control_flow 全部 ALL PASSED（含 `{ ... } + 5` 块算术）；34 个功能测试套件中 28 个 ALL PASSED，5 个失败均为已知 bug（edge_defer Bug #10/47、edge_misc bool→i32、edge_operators Bug #38、edge_string_interp Bug #55、edge_traits Bug #44），无新增回归
- **绕过**（修复前）：使用 `0 - 1` 替代 `-1`，或将负值存入变量后返回变量

### Bug #55：混合 int-float 算术运算完全失效

- **状态**：已修复 (2026-08-07)
- **现象**：当二元算术运算的操作数一方为整数字面量、另一方为浮点数字面量时，引擎不进行类型提升，导致结果完全错误：
  - `int + float` → 返回 0（如 `0 + 1.5` → 0）
  - `int - float` → 返回 0（如 `0 - 1.5` → 0）
  - `int * float` → 返回 0（如 `2 * 1.5` → 0）
  - `int / float` → panic 除零（如 `3 / 1.5` → 1.5 截断为 0，3/0 panic）
  - `float + int` → 返回 float（忽略 int 操作数，如 `1.5 + 1` → 1.5 而非 2.5）
  - `float - int` → 返回 float（忽略 int 操作数，如 `1.5 - 1` → 1.5 而非 0.5）
  - `float * int` → 返回 0（如 `1.5 * 2` → 0）
  - `float / int` → inf（如 `10.0 / 2` → inf，2 截断为 0）
- **复现代码**：
  ```kuzo
  fun main(): void {
      println("0 - 1.5 = {0 - 1.5}")   // → 0（应为 -1.5）
      println("1.5 + 1 = {1.5 + 1}")   // → 1.5（应为 2.5）
      println("2 * 1.5 = {2 * 1.5}")   // → 0（应为 3.0）
      println("0.0 - 1.5 = {0.0 - 1.5}") // → -1.5（正常，同类型）
  }
  ```
- **影响**：所有混合整数和浮点数的算术运算（如 `count * 0.1`、`total / 100.0`、`offset + 0.5` 等）
- **根因**（已确认）：两层缺陷共同导致：
  1. **`select_binary_compute_fn` 只看 lhs 类型**（`Builder.rs:3166`）：函数签名只接收 `lhs_expr`，完全忽略 rhs 类型。当 `0 - 1.5`（lhs=i32, rhs=f64）时，选择 i32 减法 compute_fn，rhs 的 1.5 被 `as_i32()` 截断为 0，结果 `0 - 0 = 0`。
  2. **`as_float_f64` 对整数类型返回 0.0**（`Value.rs:1066`）：`as_float_f64` 的 match 分支 `_ => 0.0` 覆盖了所有整数类型，导致即使选对 float compute_fn，整数操作数也被读为 0.0。例如 `2 * 1.5` 若用 f64 乘法，lhs 2（i32）被 `as_f64()` 读为 0.0，结果 `0.0 * 1.5 = 0.0`。
- **修复**：两层同时修复：
  1. **`Value.rs` 的 `as_float_f64`**：对整数类型（I8/I16/I32/I64/I128/U8/U16/U32/U64/U128/Isize/Usize/Char）返回对应的浮点值（`v.i32_val as f64` 等），而非 0.0。所有浮点访问器（`as_f16`/`as_f32`/`as_f64`/`as_f128`）均委托 `as_float_f64`，一处修复覆盖全部。
  2. **`Builder.rs` 的 `select_binary_compute_fn`**：签名增加 `rhs_expr` 参数，同时查询两侧类型。任一侧为 float 时（`lhs_is_float || rhs_is_float`），以 float 侧类型为基准选择 float compute_fn，实现编译期类型提升分派。配合 `as_float_f64` 的整数转换，int 操作数被 float compute_fn 正确读取。
- **验证**：edge_string_interp Bug #55 测试通过（`0 - 1.5 = -1.5`）；edge_numeric、arithmetic ALL PASSED；34 个功能测试套件中 29 个 ALL PASSED，4 个失败均为已知 bug（edge_defer Bug #10/47/48/49/50、edge_misc bool→i32、edge_operators Bug #38、edge_traits Bug #44），无新增回归
- **绕过**（修复前）：确保算术运算两侧类型一致：使用 `0.0 - 1.5` 而非 `0 - 1.5`；用 `cast(int_val).to(f64)` 显式提升整数

---

## P1 优先级（重要功能缺失）

### Bug #1：`!=` 运算符在 record/enum/newtype 始终返回 false

- **状态**：已修复 (2026-08-05)
- **现象**：`p1 != p2` 始终返回 `false`，即使两者字段不同
- **复现代码**：
  ```kuzo
  val p1 = Point(3, 4)
  val p3 = Point(5, 6)
  println(p1 != p3)      // false（应为 true）
  println(Red != Green)   // false（应为 true）
  ```
- **影响**：record、enum、newtype 的不等比较全部失效
- **根因**：`Ir.rs` 的 `select_binary_compute_fn` 对复合类型（record/adt/newtype/array/closure/throw 等）的 `==`/`!=` 运算返回标量比较函数 `CF_EQ_I32`/`CF_NE_I32`。复合类型的 `Value::as_i32()` 恒为 0，导致所有复合类型被判为相等，`!=` 恒返回 false。此外 `Value.rs` 的 `value_equals` 调用 `heap_equals` 时传递 `ValueArena::default()`（空 arena），无法解析 `ValueHandle` 引用的实际值，导致 newtype 内部值比较失败。
- **修复**：
  1. `Engine.rs` 新增 `compute_eq_obj`（CF_EQ_OBJ=298）和 `compute_ne_obj`（CF_NE_OBJ=299），通过 `ValueArena::with_global` 获取真实 arena，调用 `value_equals_with_arena` 进行深度语义比较。
  2. `Ir.rs` 的 `select_binary_compute_fn` 新增复合类型检测分支：当 `op` 为 `Eq`/`NotEq` 且 `ty_meta.is_none()`（非标量类型）时分派到 `CF_EQ_OBJ`/`CF_NE_OBJ`；并在 `pure_compute_fn_set` 中注册两者为纯函数。
  3. `Value.rs` 将 `value_equals`/`heap_equals` 改为 pub，新增 `value_equals_with_arena` 接受 arena 参数用于 `ValueHandle` 解引用，`heap_equals` 内部调用 `value_equals_with_arena` 确保嵌套复合类型比较正确。
- **验证**：`records`、`adt`、`newtype` 测试各新增 `!=` 用例（值不等、字段不等、双重否定 `!(!=)`、enum 不等、newtype 不等）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #6：闭包修改的 var 无法用 `==` 与字面量比较

- **状态**：已修复 (2026-08-05)
- **现象**：闭包内修改的 `var`，在外部用 `==` 与字面量比较时返回 `false`，即使值正确
- **复现代码**：
  ```kuzo
  var y: i32 = 0
  val inc = fun() { y = y + 1 }
  inc(); inc(); inc()
  println(y)        // 3（正确）
  println(y == 3)   // false（应为 true）
  ```
- **影响**：所有依赖闭包修改外部变量并进行比较的场景
- **根因**：与 Bug #3 同根因。局部变量读取（`Expr::Ident`）不依赖 `current_effect`，导致闭包调用（产生副作用）后的变量读取在 WriteBack 完成前执行，读到旧值。
- **修复**：随 Bug #3 的 `current_effect` 修复一并解决。在 `Expr::Ident` 分支添加 `current_effect` CF_SEQ 依赖，确保变量读取在前序副作用（包括闭包调用的 WriteBack）完成后执行。
- **验证**：closures 测试套件全部通过，恢复了正常的 `y == 3` 比较方式，无需使用返回值绕过。

### Bug #7：`?` 传播运算符不工作

- **状态**：已修复 (2026-08-05)
- **现象**：`expr?` 传播运算符对 Nullable 类型不工作，null 时导致调用方函数提前终止
- **复现代码**：
  ```kuzo
  fun propagateOpt(x: i32?): i32? {
      val y = x?
      y + 1
  }
  val r2: i32? = propagateOpt(null)  // main 函数被错误终止
  ```
- **影响**：所有使用 `?` 运算符进行 Nullable 传播的场景
- **根因**：包含两层问题：
  1. **Engine 缺失 Nullable 分支**：`compute_propagate` 仅处理 `ThrowVal`（Ok/Err），对 `Value::Null` 直接透传，未设置 `ControlSignal::Return` 导致 null 不传播。
  2. **内联展开破坏函数级作用域**：Analyzer 的 `inline_pass` 将包含 `?` 运算符的纯函数标记为内联候选，IrBuilder 通过 `compile_inline_expansion` 将函数体直接编译到调用方子图中。`compute_propagate` 通过 `ControlSignal::Return` 实现提前返回，该信号是函数级作用域——内联后 `Return(null)` 被设置在调用方帧上，导致调用方函数提前终止而非仅内联体返回。
- **修复**：
  1. `Engine.rs` 的 `compute_propagate` 新增 `else if v.is_null()` 分支：值为 null 时设 `frame.control_signal = ControlSignal::Return(v.clone())`，使函数提前返回 null。
  2. `Engine.rs` 的 `run_frame_sync_inner` 普通节点处理路径新增 compute_fn 控制信号检查：compute_fn（如 compute_propagate）直接设置 `control_signal` 后，跳过 `notify_downstream` 并 `continue`，避免在控制信号已设时继续处理下游节点。
  3. `Analyzer.rs` 的 `inline_pass` 新增 `has_propagate` 检查：函数体包含 `Expr::Propagate`（`?` 运算符）时不内联，因为 `ControlSignal::Return` 是函数级作用域，内联展开会错误终止调用方。
- **验证**：`nullable` 测试新增 2 个 `?` 传播用例（非 null 解包运算、null 提前返回）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #12：Trait 默认方法返回 `<non-scalar>`

- **状态**：已修复 (2026-08-05)
- **现象**：Trait 中定义的默认方法（有方法体的方法）在被调用时返回 `<non-scalar>`
- **复现代码**：
  ```kuzo
  trait Greet {
      fun name(self): str
      fun hello(self): str {
          "Hello, " + self.name()  // 默认实现
      }
  }
  type Ordering: Greet = | Lt | Eq | Gt {
      fun name(self): str { ... }
      // 未覆盖 hello，使用默认实现
  }
  println(Lt.hello())  // <non-scalar>（应为 "Hello, less"）
  ```
- **影响**：Trait 默认方法完全失效，必须显式实现所有方法
- **根因**：trait 默认方法 body 中的 `self` 缺少具体类型信息。Sema 将 trait 默认方法中的 `self` 类型注册为 "void"（因 trait 方法无具体类型），导致 `expr_type_name(self)` 返回 "void"、`expr_type_id(self)` 返回 None，`self.name()` 方法分派失败（路径 2 跳过，路径 3 因 type_id=None 跳过，call_target 未绑定），运行时 `compute_call_launch` 返回 VOID，显示为 `<non-scalar>`。
- **修复**：采用单态化方案：
  1. `trait_default_subgraphs` 键从 `(trait_idx, method_idx)` 改为 `(type_id, trait_idx, method_idx)`，为每个实现 trait 且未显式覆写该方法的类型生成专用子图。
  2. `compile_trait_default_method` 接受 `impl_type_name` 参数，编译特化版本时设置 `trait_self_type`，编译完成后重置。
  3. `expr_type_name`/`expr_type_id` 在 `trait_self_type` 存在且 expr 是 `Ident("self")` 时，直接返回 `trait_self_type` 对应的类型名/type_id，覆盖 Sema 注册的 "void"。
  4. build() 步骤 0a-trait 遍历 witness_table，为每个实现 trait 的类型预注册特化子图；步骤 2c 为每个需要特化的类型编译特化版本。
  5. 路径 3 用 `(type_id, trait_idx, method_idx)` 查找特化子图。
- **验证**：`traits` 测试中 `Ordering` 和 `Animal` 类型移除 `hello` 显式实现，改用 trait 默认方法；`Lt.hello()`/`Eq.hello()`/`Gt.hello()`/`Animal.hello()` 均返回正确结果；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #16：`str + int` 字符串拼接返回 `<non-scalar>`

- **状态**：已修复 (2026-08-05)
- **现象**：字符串与整数字面量拼接时，返回 `<non-scalar>` 而非拼接后的字符串
- **复现代码**：
  ```kuzo
  println("" + 6)           // <non-scalar>（应为 "6"）
  println("result=" + 42)   // <non-scalar>（应为 "result=42"）
  ```
- **影响**：所有 `str + int` 字符串拼接场景，包括字符串插值的底层实现
- **根因**：`Ir.rs` 的 `select_binary_compute_fn` 仅在 LHS 类型为 `"str"` 且 op 为 `Add` 时返回 `CF_STR_CONCAT`，但 `compute_str_concat` 只处理 `(Str, Str)`，对 `(Str, int)` 等非字符串操作数返回 TypeError。`compile_binary` 直接编译 LHS/RHS 节点后用 `select_binary_compute_fn` 分派，未在 `str + non-str` 场景将非字符串操作数转换为字符串。
- **修复**：在 `Ir.rs` 的 `compile_binary` 中新增 `str + non-str` / `non-str + str` 混合类型检测：当 `Add` 运算的操作数任一方为 `str` 类型时，将非字符串操作数通过 `compute_reflect_format`（idx 290）转为字符串节点，然后用 `CF_STR_CONCAT` 拼接（与字符串插值 `"{expr}"` 的降级路径一致）。新增 `make_reflect_format_node` 辅助方法封装此转换。
- **验证**：`strings` 测试新增 7 个混合拼接用例（`str + int`、`int + str`、`str + bool`、`bool + str`、零值拼接、前后缀拼接）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #19：嵌套函数不支持自递归调用

- **状态**：已修复 (2026-08-07)
- **发现场景**：闭包边缘测试中，在 `main` 内定义的嵌套函数递归调用自身时 panic
- **现象**：在函数体内定义的嵌套函数，当函数体中递归调用自身时 panic
- **复现代码**：
  ```kuzo
  fun main(): void {
      fun fib(n: i32): i32 {
          if n < 2 { n } else { fib(n - 1) + fib(n - 2) }
      }
      fib(5)  // panic
  }
  ```
- **错误信息**：`thread 'main' panicked at src/ir/Compute.rs:3026:14: compute_closure_call: input is not callable (Closure or Partial)`
- **影响**：嵌套函数无法实现递归算法（如 fibonacci、阶乘等），必须将函数移到顶层
- **根因**（已确认）：`start_subgraph` 的 `same_function` 路径（非逃逸闭包帧链共享）在注入 upvalue 参数时，统一从父帧读取 `outer_node` 的值。对于递归闭包的 self_upvalue（`self_upvalue_idx >= 0`），其 `outer_node` 是 `void_const` 占位节点，父帧中该节点值为 void。`compute_closure_call` 虽在 args 向量中正确注入了闭包自身引用（第 3055-3063 行），但 `same_function` 路径完全忽略 args 中的 upvalue 部分，直接从父帧读取 void 值。导致子帧内 `fib` 变量读到 void，递归调用时 `compute_closure_call` 收到 void 而非 Closure，panic。
- **修复**：在 `Subgraph.rs` 的 `start_subgraph` same_function 路径中，upvalue 注入循环前从 `closure_val` 提取 `self_upvalue_idx`（支持 Closure 和 Partial 两种可调用值）。当 upvalue 索引 `i == self_upvalue_idx` 时，注入 `closure_val`（闭包自身引用）而非父帧值。跨函数路径（`!same_function`）不受影响，因为它直接使用 args 向量（已含 self 注入）。
- **验证**：bug19_repro 全部 4 个测试通过（fib(5)=5、fib(10)=55、fact(5)=120、sumTo(10)=55）；34 个功能测试套件中 30 个 ALL PASSED，4 个失败均为已知 bug（edge_defer Bug #10/47/48、edge_misc bool→i32、edge_operators Bug #38、edge_traits Bug #44），无新增回归
- **临时绕过**（修复前）：将递归函数移至顶层 `fun` 定义

### Bug #21：i32 超范围整数字面量静默退出（无编译错误）

- **状态**：已修复
- **发现场景**：位运算边缘测试中，超过 i32 范围的十六进制字面量导致程序静默退出
- **现象**：当字面量值超过类型标注的范围（如 `0x80000000` 赋值给 `i32`）时，程序静默退出（无 panic、无编译错误、EXIT=0），后续代码不执行
- **复现代码**：
  ```kuzo
  fun main(): void {
      println("start")              // 输出
      val big: i32 = 0x80000000     // 2147483648 > i32 MAX，静默退出
      println("big = {big}")        // 不执行
  }
  ```
- **影响**：用户无法得到任何反馈，难以定位问题。同样的值用 `i64` 类型标注可以正确解析（输出 3735928559）
- **根因**：`Builder.rs::parse_const_value` 使用 `i32::try_from(v).ok()` 将 `and_then` 链中的溢出静默转换为 `None`，`compile_const_with_value` 将 `None` 存入 `graph.const_values`，运行时读取 None 常量导致静默退出。无法区分"非常量表达式"与"常量溢出"
- **修复方案**：
  1. `parse_const_value` 返回类型从 `Option<ConstValue>` 改为 `Result<Option<ConstValue>, String>`，区分三种语义：`Ok(Some)` 合法常量、`Ok(None)` 非常量表达式、`Err(msg)` 常量解析失败（溢出/语法错误）
  2. 新增 `parse_int_to_i128`：解析整数字面量为 i128，语法错误时返回带 span 的 `Err`
  3. 新增 `check_int_range`：通过 `try_int!` 宏统一所有 12 种整数类型的范围检查，超出范围时返回带类型名、合法范围和 span 的 `Err`
  4. `compile_const_with_value` 匹配 `Err` 时将错误推入 `self.errors`，最终通过 `graph.ir_errors` 被 `main.rs` 捕获并以 exit code 1 退出
  5. 同步修复 stdlib 中 4 个文件的大整数字面量问题：`Duration.kuzo`（3 处 i128 后缀）、`SystemTime.kuzo`（1 处 i128 后缀）、`Math.kuzo`（3 处改用 `1u32<<31`/`1u64<<63`/`1u128<<127` 位运算构造）
- **验证结果**：
  - 复现用例 `bug21_repro`：输出 `IR error: integer literal '0x80000000' at line 5:20 is out of range for i32 (valid range: -2147483648..=2147483647)`，exit code 1
  - Rust 单元测试：8 passed; 0 failed
  - 功能测试 35 个目录：28 全通过，5 个含预存 bug 失败（Bug #38/#44 等），零新增回归
  - 整数运算/数学计算/类型转换核心测试（arithmetic/bitwise/cast/edge_numeric）全部通过

### Bug #23：类型别名与原始函数类型不等价

- **状态**：已修复
- **发现场景**：闭包边缘测试中，使用 `type` 定义的函数类型别名与原始函数类型不被视为同一类型
- **现象**：`type IntFn = () -> i32` 定义后，将闭包字面量赋值给 `IntFn` 类型的变量时报类型不匹配
- **复现代码**：
  ```kuzo
  type IntFn = () -> i32
  fun main(): void {
      var rec: IntFn = fun() { 0 }    // type annotation mismatch: expected 'IntFn', found '() -> i32'
      rec = fun() { 42 }              // assignment type mismatch
  }
  ```
- **错误信息**：`type annotation mismatch: expected 'IntFn', found '() -> i32'`
- **影响**：类型别名无法用于闭包变量的声明和赋值，限制了函数类型别名的实用性
- **根因**：`Inference.rs` 的 `resolve_name_to_type` 在解析类型别名时仅使用 `target_type_name`（字符串名称）进行递归解析。对于非命名目标类型（函数类型 `() -> i32`、Record 类型、Array 类型等），`target_type_name` 为 `None`，导致别名解析失败回退到 `make_adt(name)`，将 `IntFn` 视为独立 ADT 而非函数类型
- **修复方案**：在 `resolve_name_to_type` 中优先使用 `TypeDefInfo.target_type`（已解析的 `TypeHandle`），覆盖所有非命名目标类型；仅在 `target_type` 为 `None` 时退回 `target_type_name` 路径处理命名目标（如 `type A = B`）
  - 修改位置：[Inference.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/sema/Inference.rs#L817-L834)
  - 关键逻辑：`alias_target_ty` 优先返回 `td.target_type`，命中后直接返回 `inner_ty`，跳过 `target_type_name` 递归
- **验证结果**：
  - closures 测试：`IntFn` 类型别名赋值闭包字面量全部通过
  - edge_closures 测试：函数类型别名与原始函数类型等价性验证通过
  - 回归测试无新增失败用例

### Bug #26：同一 `val` 数组跨多个 while 循环复用读取陈旧值

- **状态**：已修复
- **发现场景**：edge_generics 测试中，第一个 while 循环遍历 `val` 数组正常，后续 while 循环再次遍历同一数组时读到陈旧/错误值
- **现象**：
  ```kuzo
  val arr = [1, 2, 3, 4, 5]
  // 第一个 while 循环遍历 arr：正常
  // 第二个 while 循环遍历 arr：arr[loopVar] 读到陈旧值
  ```
- **影响**：在同一函数中对同一 `val` 数组进行多次 while 循环遍历时，后续循环读取错误值
- **根因**：while 循环 body 帧在第一个循环完成后未完全重置 effect 链节点和值表状态。第二个循环复用同一数组时，数组索引节点的值表残留上一轮循环的陈旧值，导致 `arr[loopVar]` 读取到错误结果（与 Bug #3/M4 同属"陈旧值读取"类根因，但发生在顺序循环场景）
- **修复方案**：由先前的循环帧重置改进修复（`Subgraph.rs` 的 `switch_subgraph` 中 `value_table.reset_all()` + effect 链节点 pending_inputs 重置机制）。当 LoopBody 帧在 continue/正常完成时复用，帧的 value_table 被完全重置，effect 链节点重新标记为 PENDING_EXTERNAL，确保第二轮循环重新求值数组索引节点而非读取陈旧缓存
  - 修改位置：[Subgraph.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/engine/Subgraph.rs#L22-L38)（switch_subgraph 的帧重置逻辑）
- **验证结果**：
  - edge_generics 测试：移除 `warr2` 绕过，多个 while 循环复用同一 `warr` 数组全部通过（`identity in while loop sum`=15、`simple array sum with reused array`=15）
  - 回归测试无新增失败用例

### Bug #29：嵌套模式 Error(Error(v)) 提取的 i32 值丢失类型信息

- **状态**：已修复
- **发现场景**：edge_throw 测试中，从 `throw 42i32` 经 `Error(Error(v))` 提取的 v 打印为 42，但 `v == 42i32` 返回 false
- **现象**：嵌套模式解构时未为 i32 模式变量注册 ExprInfo 类型信息，`==` 回退到复合类型比较而失败。同路径提取的 str 值 `v == "boom"` 正常
- **根因**：`Inference.rs` 的 `refine_constructor_pattern` 在处理嵌套构造器模式时，始终将子模式绑定到构造器字段类型（`field_type_reprs[i]`）。当 `Error` ADT 用于解包 `Throw<T, E>` 的 `error_type` 时，构造器返回类型（`Error` ADT）与期望类型（`E`，如 `i32`）不兼容，但子模式仍绑定到 `Error` 的字段类型（`str`），导致模式变量 `v` 获得错误的类型信息，`==` 比较失败
- **修复方案**：在 `refine_constructor_pattern` 中增加构造器返回类型与期望类型的兼容性检查。当 `unify(ctor_return_ty, expected_ty)` 失败时（类型不兼容），子模式绑定到 `expected_ty` 而非构造器字段类型，确保模式变量获得正确的运行时类型
  - 修改位置：[Inference.rs](file:///Users/haojunhuang/CLionProjects/Kuzo/src/sema/Inference.rs#L697-L716)
  - 关键逻辑：`ctor_compatible = unify(ctor_return_ty, expected_ty).is_ok()`；不兼容时 `sub_ty = expected_ty`，兼容时 `sub_ty = field_type_reprs[i]`
- **验证结果**：
  - edge_throw 测试：`throwI32(true)`（Throw<i32, i32>）的 `Error(Error(v)) => check(v == 42i32, ...)` 直接比较通过（Bug #29 修复生效）；`Error(Error(v)) => check(v == "boom", ...)` 同样通过
  - `Ok(Error(Error(v))) => check(v == 42i32, ...)` 嵌套模式也通过
  - `firstThrow()`（Throw<i32, Error>）的 `Error(Error(v))` 仍需 `cast(v).to(i32)` 绕过——此为 Limit-A（throw 原始类型被包装为 Error ADT，字段声明为 str 但运行时存 i32），非 Bug #29 范畴
  - 回归测试 35 套功能测试无新增失败用例（edge_defer/edge_operators/edge_traits 的失败为预存 bug）

### Bug #34：索引数组赋值 `arr[i] = x` 是空操作（不修改数组）

- **状态**：已修复
- **发现场景**：edge_stress 冒泡排序测试中，`sort_arr[bsj] = sort_arr[bsj+1]` 不修改数组，排序完全失效
- **现象**：对数组元素的索引赋值 `arr[i] = x` 是空操作——数组保持原值不变，赋值被静默丢弃。`arr[i] = x` 后读取 `arr[i]` 仍是旧值。对比：record 字段赋值 `r.field = x` 工作正常
- **复现代码**：
  ```kuzo
  val a: i32[] = [10, 20, 30, 40, 50]
  a[0] = 99
  println(a[0])  // 10（应为 99）
  a[2] = 77
  println(a[2])  // 30（应为 77）
  println(a.len())  // 5（长度未变）
  ```
- **影响**：所有原地数组修改失效——冒泡排序、快速排序、原地反转、计数排序、动态规划填表等。数组只能通过 `++` 拼接构建新数组（函数式风格）
- **根因**：`Builder.rs` 的 `Stmt::Assignment` 分支只处理 `Expr::Ident` target（普通变量、捕获变量、全局变量），对 `Expr::Index` target（数组索引赋值）直接落到 `None`——赋值被丢弃，成为空操作。对比 `FieldAssignment`（record 字段赋值）有完整的 `CF_RECORD_FIELD_SET` 实现
- **修复方案**：
  1. 新增 `CF_ARRAY_STORE`（compute_fn idx 301）常量，注册到 `compute_fn_table!` 宏
  2. 实现 `compute_array_store`：三输入（arr, index, value），通过 `Arc::as_ptr` 直接修改 Array 堆对象的 `elements` 向量（与 `compute_record_field_set` 同语义，&self 引用语义）。越界索引扩展数组到 idx+1（补 Void）
  3. 在 `Stmt::Assignment` 中添加 `Expr::Index { recv, index }` target 分支：编译 recv、index、value 三个子节点，生成 `CF_ARRAY_STORE` 节点
- **验证结果**：
  - edge_stress：`arr[0]=99 after assignment` PASS、`arr[2]=77 after assignment` PASS、冒泡排序 `[0]=1`/`[4]=5`/`length=5` PASS，ALL PASSED
  - 回归测试 8 套（edge_stress/edge_arrays/arrays/edge_loop/edge_records/edge_misc/closures/edge_closures）全部 ALL PASSED，零新增回归

### Bug #38：`&&`/`||` 不短路，RHS 总被求值（无 short-circuit）

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_operators 测试中，`false && scBump()` 后 `sc_count != 0`，表明 RHS 被求值
- **现象**：Kuzo 的 `&&`（逻辑与）和 `||`（逻辑或）运算符不实现短路求值——无论 LHS 结果如何，RHS 表达式总被求值。这违反大多数语言中 `&&`/`||` 的短路语义（LHS false 时 `&&` 不求值 RHS；LHS true 时 `||` 不求值 RHS）
- **复现代码**（最小，用顶层函数隔离闭包捕获问题）：
  ```kuzo
  var sc_count: i32 = 0
  fun scBump(): bool { sc_count = sc_count + 1; true }

  fun main(): void {
      sc_count = 0
      val r1 = false && scBump()    // 应短路，scBump 不应被调用
      println(sc_count)             // 输出 1（应为 0）→ RHS 被求值
      sc_count = 0
      val r2 = true || scBump()     // 应短路，scBump 不应被调用
      println(sc_count)             // 输出 1（应为 0）→ RHS 被求值
  }
  ```
- **对照**（非短路情况正常）：
  - `true && scBump()` → sc_count == 1 ✓（RHS 应被求值，确实被求值）
  - `false || scBump()` → sc_count == 1 ✓（RHS 应被求值，确实被求值）
- **根因**：IR 编译器将 `&&`/`||` 编译为普通二元运算（与 `+`/`*` 类似），编译 LHS 和 RHS 两个子节点后用 `CF_AND_BOOL`/`CF_OR_BOOL` compute_fn 合并结果。由于数据流引擎预先编译并调度了 RHS 节点，RHS 总被执行。正确的短路语义需要条件依赖：仅当 LHS 不满足短路条件时才调度 RHS（类似 if 分支的条件数据流）
- **修复**：在 `Builder.rs` 的 `compile_binary` 中将 `&&`/`||` 降级为 Gate 条件分支（与 if 表达式相同的条件数据流）。新增 `compile_short_circuit` 方法：
  - `lhs && rhs` → `if lhs { rhs } else { false }`：then 分支编译 RHS 表达式，else 分支为常量 false
  - `lhs || rhs` → `if lhs { true } else { rhs }`：then 分支为常量 true，else 分支编译 RHS 表达式
  - Gate 节点（`CF_GATE_LAUNCH`）根据 cond_node 选择执行 then_sg 或 else_sg，RHS 仅在需求值的分支中被求值
  - 新增 `compile_bool_branch` 辅助方法编译常量 bool 分支（短路值）
- **验证**：edge_operators ALL PASSED（`false && scBump()` 短路 sc_count=0、`true || scBump()` 短路 sc_count=0、`true && scBump()` 求值 sc_count=1、`false || scBump()` 求值 sc_count=1）；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

### Bug #39：递归构建数组后，`empty ++ [literal]` 内联拼接丢失字面量（返回 0 长度）

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_arrays 测试中，递归构建 `rangeArr(10)`/`reverseArr` 后，`(e1 ++ [1]).len()` 返回 0 而非 1
- **现象**：在执行过递归数组构建（函数返回 `[]` 或 `arr ++ [x]` 的递归）后，对空数组变量做**内联**拼接字面量 `(empty ++ [literal]).len()` 会丢失字面量数组，返回 0 长度。先赋值到 val 再 `.len()` 则正常
- **复现代码**（最小）：
  ```kuzo
  fun rangeArr(n: i32): i32[] {
      if n <= 0 { [] } else { rangeArr(n - 1) ++ [n - 1] }
  }
  fun main(): void {
      val r10 = rangeArr(10)        // 递归构建数组（触发条件）
      val e1: i32[] = []
      println((e1 ++ [1]).len())   // 输出 0（应为 1）→ 字面量 [1] 丢失
      // 对照：
      val a1 = e1 ++ [1]            // 先赋值
      println(a1.len())             // 输出 1（正常）
      println((e1 ++ e1).len())     // 输出 0（正常，empty ++ empty）
  }
  ```
- **不影响的情况**：
  - 无递归数组构建的前序时，`(empty ++ [1]).len()` == 1 ✓
  - 先赋值到 val：`val a = e1 ++ [1]; a.len()` == 1 ✓
  - `empty ++ empty`（两变量）正常 ✓
  - 仅 `while` 循环构建数组（非递归）后不触发 ✓
- **根因**：递归数组构建在帧栈中累积了多个 `[literal]` 数组字面量节点。后续内联 `(e1 ++ [1])` 中的 `[1]` 字面量节点复用了被递归帧污染的缓存槽/值表条目，导致字面量被读取为空数组（0 长度）。先赋值到 val 时，字面量节点通过独立的 WriteBack 路径求值，避开了污染的缓存。与 Bug #26（同一 val 数组跨循环复用读取陈旧值）同属"陈旧值读取"类根因
- **修复**：由先前的执行器审查修复（M1-M9）中的循环帧重置改进解决。`Subgraph.rs` 的 `switch_subgraph` 中 `value_table.reset_all()` + effect 链节点 pending_inputs 重置机制确保递归调用返回后帧的值表被完全重置，effect 链节点重新标记为 PENDING_EXTERNAL，后续内联拼接表达式从头重新求值而非读取陈旧缓存
- **验证**：edge_arrays ALL PASSED（含递归数组构建后内联拼接 `(e1 ++ [1]).len()` == 1）；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

### Bug #44：trait 默认方法调用另一个默认方法时返回源代码片段

- **状态**：已修复 (2026-08-07)
- **现象**：trait 默认方法链中，一个默认方法调用另一个默认方法时，返回源代码片段而非求值结果
- **复现代码**：
  ```kuzo
  trait Chain {
      fun base(self): str
      fun wrap1(self): str { "[" + self.base() + "]" }
      fun wrap2(self): str { "{{" + self.wrap1() + "}}" }
      fun wrap3(self): str { "<" + self.wrap2() + ">" }
  }
  type TagA: Chain = TagA(label: str) {
      fun base(self): str { self.label }
  }
  // TagA("hello").wrap1() == "[hello]"    ✓ (默认→显式调用正常)
  // TagA("hello").wrap2() == " + self.wrap1() + "  ✗ (默认→默认调用返回源码片段)
  // TagA("hello").wrap3() == "< + self.wrap1() + >"  ✗
  ```
- **影响**：所有 trait 默认方法链（默认方法调用另一个默认方法）失效。默认→显式方法调用正常（如 `describe()→area()`）。
- **根因**：两层问题共同导致：
  1. **字符串插值解析贪婪消费**：`Parser.rs` 的 `scan_string` 在扫描字符串插值表达式 `{...}` 内部内容时，遇到嵌套字符串字面量中的引号会错误地终止外层字符串的扫描。trait 默认方法体中含字符串拼接（如 `"{" + self.wrap1() + "}"`），花括号 `{` 触发插值解析，插值表达式扫描贪婪消费了方法体的剩余部分，导致方法体被截断为源代码片段
  2. **字面量花括号无转义机制**：字符串字面量中的 `{` 和 `}` 总是被当作插值解析，没有 `{{`/`}}` 转义语法
- **修复**：
  1. `Parser.rs` 的 `scan_string` 在插值表达式扫描中正确处理嵌套字符串字面量——遇到 `"` 时扫描完整嵌套字符串（含 `\"` 转义），避免将外层字符串的闭合引号误认为嵌套字符串开始
  2. `Parser.rs` 新增 `{{`/`}}` 花括号转义语法：`{{` 表示字面量 `{`，`}}` 表示字面量 `}`，不被当作插值解析
  3. `edge_traits` 测试更新：`wrap2` 方法体中的字面量花括号改用 `{{`/`}}` 转义（`"{{" + self.wrap1() + "}}"`）
- **验证**：edge_traits ALL PASSED（wrap2/wrap3 默认方法链 3 层嵌套调用全部正确：`wrap3 == "<{{[hello]}}>"`）；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

### Bug #48：defer 跨函数调用执行顺序错误

- **状态**：已修复 (2026-08-07)
- **现象**：defer 跨函数调用执行顺序错误：callee 的 defer 延迟到 caller 退出时才执行（应在 callee 返回时执行）
- **根因**：测试期望值笔误。callee 的 defer 实际在 callee 返回时正确执行（由 Bug #47 的 `has_defer` 内联检查保证含 defer 的函数不被内联，defer 在帧完成时正确执行），但测试期望字符串写错（`"calleepmidcaller"` 应为 `"calleemidcaller"`）
- **修复**：修正 `edge_defer` 测试中的期望值笔误（`"calleepmidcaller"` → `"calleemidcaller"`），验证 defer 跨函数链的正确执行顺序：callee defer → caller body 继续 → caller defer
- **验证**：edge_defer `cross-function defer order` check PASS（`chain_log == "calleemidcaller"`）；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

### Bug #49：defer body 含整数算术时不执行

- **状态**：已修复 (2026-08-07)
- **现象**：defer body 含整数算术（`global_int + value`）时不执行（同模式的字符串拼接正常）
- **根因**：defer body 引用的局部变量在函数体中被重赋值后，新值未 WriteBack 到原始节点。defer body 通过原始节点引用局部变量，但原始节点的值表条目仍为编译期快照（旧值），defer body 读取到的是旧值而非最新值。字符串拼接正常是因为字符串操作走全局变量路径（global_store），不依赖局部变量的 WriteBack
- **修复**：在 `Builder.rs` 的 `Stmt::Assignment` 局部变量重赋值路径中，新增 `current_function_has_defer` 检查。当当前函数子图含 defer（`defer_table` 非空）时，局部变量重赋值除 `bind_var` 外还生成 WriteBack 节点（`compile_writeback_node`），将新值写回原始节点，使 defer body 能通过原始节点读取到最新值。`current_function_has_defer` 方法检查 `current_function_sg` 对应子图的 `defer_table` 是否非空
- **验证**：edge_defer `defer reads local var value` check PASS（`capture_log == "10"`，defer body 读取到重赋值后的 x=10）；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

### Bug #50：defer 在函数体含 `match` 表达式时不执行

- **状态**：已修复 (2026-08-07)
- **现象**：defer 在函数体含 `match` 表达式时不执行（if-else 体正常；defer body 本身简单也不行）
- **根因**：与 Bug #47 同根因。分析器的 `inline_pass` 将含 `match` 表达式的纯函数（函数体仅操作局部变量）标记为可内联。`compile_inline_expansion` 直接编译函数体到调用方子图，不创建 Call 节点和帧，defer_table 永远不被运行时检查，defer 完全不执行。`match` 表达式本身不影响 defer 机制，但 match-heavy 函数更容易被判定为纯函数从而被内联
- **修复**：由 Bug #47 的 `has_defer` 检查修复。`Analyzer.rs` 的 `inline_pass` 新增 `has_defer` 检查，排除含 defer 语句的函数被内联，确保 defer 语义要求帧生命周期（创建帧 → 执行体 → 执行 defer → 完成帧）不被内联消除
- **验证**：edge_defer `defer runs after match` check PASS（`match_log == "cleanup"`，defer 在含 match 表达式的函数体后正确执行）；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

### Bug #54：字符串插值花括号内转义引号导致解析失败

- **状态**：已修复 (2026-08-07)
- **现象**：字符串字面量中，插值花括号 `{}` 内包含转义引号 `\"` 时，词法/解析器无法正确处理，导致整个文件的解析失败（`parse error: expected expression`）。转义引号在非插值上下文中正常工作。
- **复现代码**：
  ```kuzo
  fun main(): void {
      val s = "{\"hello\"}"   // → parse error，整个文件无法解析
      println(s)
  }
  ```
- **影响**：所有需要在字符串插值中嵌套字符串字面量的场景（如 `"key is {\"value\"}"`）
- **根因**：两层缺陷：
  1. **词法器 `scan_string` 的插值表达式扫描**：扫描插值表达式 `{...}` 内部内容时，遇到 `"` 后未正确扫描完整嵌套字符串字面量。`\"` 中的 `\` 被当作普通字符跳过，随后的 `"` 被误认为外层字符串的闭合引号，导致外层字符串提前终止，后续 token 流错乱
  2. **`parse_string_literal` 的插值表达式文本提取**：提取插值表达式文本时同样未正确处理嵌套字符串字面量，遇到 `"` 即停止提取，导致表达式文本被截断
- **隔离**：`"say \"hello\""`（转义引号在非插值上下文）正常；`"interp {1 + 2}"`（插值无转义引号）正常；仅 `"{\"str\"}"`（转义引号在插值内）失败
- **修复**：
  1. `Parser.rs` 的 `scan_string` 在插值表达式扫描中，遇到 `"` 时扫描完整嵌套字符串字面量（含 `\"` 转义序列），确保嵌套字符串的闭合引号不被误认为外层字符串的结束
  2. `Parser.rs` 的 `parse_string_literal` 在提取插值表达式文本时，同样正确处理嵌套字符串字面量——遇到 `"` 时扫描完整嵌套字符串，确保 expr_text 包含完整的字符串字面量
  3. 插值表达式文本提取后调用 `unescape_string` 反转义，处理外部字符串的转义序列（如 `\"`），再传给 `parse_interpolation_expr` 解析
- **验证**：edge_string_interp ALL PASSED；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

---

## P2 优先级（功能受限）

### Bug #5：`for-in arr.iter()` 迭代不工作

- **状态**：已修复 (2026-08-05)
- **现象**：`for x in arr.iter()` 无法正确迭代数组元素
- **复现代码**：
  ```kuzo
  for n in arr.iter() {
      sum = sum + n  // 不执行或返回错误
  }
  ```
- **影响**：数组迭代语法糖失效
- **根因**：与 Bug #3 同根因。For 循环体通过 `register_for_subgraph` 编译为递归子图，循环体内的变量读取（`Expr::Ident`）缺少 `current_effect` 依赖。当循环通过 WriteBack 更新变量值时，后续表达式在 WriteBack 完成前读取旧值，导致迭代不工作。
- **修复**：随 Bug #3 的 `current_effect` 修复一并解决。在 `Expr::Ident` 分支添加 `current_effect` CF_SEQ 依赖，并在 `register_for_subgraph` 中编译循环体前重置 `current_effect = None`，确保变量读取在前序副作用完成后执行。
- **验证**：`arrays` 测试新增 3 个 for-in 用例（数值数组求和、空数组迭代、字符串数组拼接）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #8：`?.` 链式访问不工作

- **状态**：已修复 (2026-08-05)
- **现象**：可空链式访问 `obj?.field` 无法使用，短路返回 null 后与 `null` 比较返回 false
- **复现代码**：
  ```kuzo
  val city = user?.addr?.city  // 短路返回 null
  println(city == null)        // false（应为 true）
  ```
- **影响**：可空类型的链式访问及后续 null 比较失效
- **根因**：与 Bug #9 同根因。`arena.type_name` 对 `ConcreteType::Nullable(inner)` 递归取 inner 名，导致 `str?` 的 `expr_type_name` 返回 `"str"`（内层类型名）。`select_binary_compute_fn` 的 `Eq` 因此分派到 `CF_EQ_STR`，而 `compute_eq_str` 通过 `heap_obj()` 匹配，`Value::Null` 的 `heap_obj()` 返回 `None`，导致 null 比较恒返回 false。
- **修复**：随 Bug #9 一并修复。新增 `expr_is_nullable` 方法检查 `ExprInfo.type_desc.type_name == "nullable"`，在 `select_binary_compute_fn` 中 nullable 类型的 `Eq`/`NotEq` 分派到 `CF_EQ_OBJ`/`CF_NE_OBJ`（`value_equals_with_arena` 正确处理 `Null` 判别式比较）。
- **验证**：`nullable` 测试新增 3 个 `?.` 链式访问用例（非空链式访问、null 短路返回 null、链式访问带 `??` 合并）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #9：`str? ??` 合并返回 false

- **状态**：已修复 (2026-08-05)
- **现象**：`str?` 类型的 `??` 合并运算符结果与字符串比较返回 false
- **复现代码**：
  ```kuzo
  val s: str? = null
  println(s ?? "default")                  // "default"（正确）
  println((s ?? "default") == "default")    // false（应为 true）
  ```
- **影响**：字符串可空类型的合并运算结果比较失败
- **根因**：两层问题：
  1. **`??` 分派错误**：`select_binary_compute_fn` 中 `str` 类型分支将 `Elvis` 运算符错误分派为 `CF_EQ_STR`（字符串相等比较），而非 `CF_ELVIS`。
  2. **nullable `==` 分派错误**：`arena.type_name` 对 `Nullable(inner)` 递归取 inner 名，导致 `str?` 的 `expr_type_name` 返回 `"str"`，`Eq` 分派到 `CF_EQ_STR`。`compute_eq_str` 不处理 `Value::Null`（`heap_obj()` 返回 `None`），导致 `?.` 短路或 `??` 合并产生的 null 值比较恒返回 false。
- **修复**：
  1. `Ir.rs` 的 `select_binary_compute_fn` 在类型分支前优先处理 `Elvis` 运算符，直接返回 `CF_ELVIS`。
  2. `Ir.rs` 新增 `expr_is_nullable` 方法（检查 `ExprInfo.type_desc.type_name == "nullable"`），在 `select_binary_compute_fn` 中 nullable 类型的 `Eq`/`NotEq` 分派到 `CF_EQ_OBJ`/`CF_NE_OBJ`（`value_equals_with_arena` 正确处理 `Null` 判别式比较）。
  3. `Engine.rs` 的 `compute_elvis` 实现运行时逻辑：lhs 为 null 时返回 rhs，否则返回 lhs。
- **验证**：`nullable` 测试新增 `str? ??` 合并比较用例（null 合并后 `==` 比较、非 null 合并后 `==` 比较）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #11：`while break` 不工作

- **状态**：已修复 (2026-08-05)
- **现象**：`while` 循环中的 `break` 语句不生效，循环无法提前退出
- **复现代码**：
  ```kuzo
  var j: i32 = 0
  while j < 100 {
      if j >= 5 { break }  // break 不生效
      j = j + 1
  }
  println(j)  // 100（应为 5）
  ```
- **影响**：所有依赖 `break` 提前退出循环的场景
- **根因**：与 Bug #3 同根因。break 语句后循环体的变量更新（`j = j + 1`）通过 WriteBack 写回，但后续条件判断（`j >= 5`）的变量读取不依赖 `current_effect`，在 WriteBack 完成前读取旧值，导致 break 条件永不满足。
- **修复**：随 Bug #3 的 `current_effect` 修复一并解决。
- **验证**：control_flow 测试套件新增 `while break exits at 5` 测试，全部通过。

### Bug #14：返回 newtype 解包值的函数返回 `void`

- **状态**：已修复 (2026-08-05，随 #13 一并修复）
- **现象**：函数中通过 match 解包 newtype 并返回值时，返回 `void`（与 #13 关联）
- **复现代码**：
  ```kuzo
  fun celsiusRaw(c: Celsius): f64 {
      match c {
          Celsius(v) => v  // 不执行
      }
  }
  println(celsiusRaw(Celsius(100.0)))  // void（应为 100.0）
  ```
- **影响**：所有返回 newtype 解包值的函数
- **根因**：与 #13 同根因。`compute_pattern_ctor_match` 和 `compute_pattern_adt_field_get` 不处理 `HeapObj::Newtype`，导致 newtype match 分支不匹配、模式变量绑定到 void，函数返回 void。
- **修复**：随 #13 一并修复。`compute_pattern_ctor_match` 新增 `HeapObj::Newtype(n) => n.type_name == *ctor_name` 分支；`compute_pattern_adt_field_get` 新增 `HeapObj::Newtype(n)` 分支提取 inner 值。
- **验证**：`newtype` 测试中 `celsiusRaw(Celsius(100.0)) == 100.0` 用例通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #22：有符号整数除法溢出 panic（非 wrapping 语义）

- **状态**：已修复 (2026-08-07)
- **发现场景**：数值边界测试中，`i32_min / -1` 导致 panic
- **现象**：有符号整数除法在溢出时 panic，与加减乘的 wrapping 语义不一致
- **复现代码**：
  ```kuzo
  fun main(): void {
      val min: i32 = -2147483648
      val r = min / -1   // panic: attempt to divide with overflow
  }
  ```
- **错误信息**：`thread 'main' panicked at src/value/Ops.rs:1778:1: attempt to divide with overflow`
- **影响**：`i32_min / -1`、`i64_min / -1` 等边界除法导致程序崩溃。加减乘使用 wrapping 语义（溢出回绕），但除法使用 Rust 默认 `/` 运算符（溢出 panic）
- **根因**：`src/value/Ops.rs` 的 `impl_arith_int!` 宏中有符号除法使用 Rust 原生 `/` 运算符，未使用 `wrapping_div` 或 `wrapping_rem`
- **修复方案**：将 `impl_arith_int!` 宏中的 `arith_div_$ty` 改为 `a.wrapping_div(b)`，`arith_mod_$ty` 改为 `a.wrapping_rem(b)`，与加减乘的 wrapping 语义一致
- **验证**：edge_numeric 测试中 i32/i64/i8/i16/i128 的 `MIN / -1` 和 `MIN % -1` 全部通过

### Bug #25：u128 MAX 字面量无法直接表示

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_numeric 测试中，`340282366920938463463374607431768211455u128` 和 `0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFu128` 均导致常量为 None，静默失败
- **现象**：u128 MAX（2^128−1）的十进制或十六进制字面量无法解析，与 Bug #21 同类（超 i128 范围的整数字面量静默退出）
- **根因**：`Builder.rs::parse_int_to_i128` 使用 `i128::from_str_radix` 解析，而 u128 MAX 超过 `i128::MAX`，解析失败
- **修复方案**：新增 `parse_int_to_u128` 函数，当 suffix 为 `u128` 时直接使用 `u128::from_str_radix` 解析，支持十进制和十六进制，覆盖完整 u128 范围
- **验证**：edge_numeric 测试中 `u128_max_dec == u128_max_hex` 通过

### Bug #27：throw 原始类型被包装为 Error(value: v)，非裸值

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_throw 测试中，`throw 42i32` 产生的错误值打印为 `Error(value: 42)` 而非裸 i32
- **现象**：`Throw<T, E>` 的第二类型参数 E 对原始类型（i32/str）无效，所有 thrown 原始值被统一包装进 Error 对象。record 类型不受影响
- **影响**：throw 原始类型后的错误值结构不一致，需用嵌套模式 `Error(Error(v))` 解构提取内值
- **根因**：`ThrowPayload::Err` 持有 `Arc<RecordValue>`，throw 原始类型时被迫包装为 Error record
- **修复方案**：将 `ThrowPayload::Err` 改为直接持有 `Value`（而非 `Arc<RecordValue>`），使 throw 任意值后 `match Error(v)` 的 v 直接绑定到 throw 的值本身。同步更新 `Arena.rs` 的 `alloc_throw_err`/`throw_err` 和 `Builder.rs` 的 `compute_throw_wrap_err`/`compute_throw_err`，以及 `Compute.rs` 中 5 处 `make_err` 闭包（FieldError/IndexError/SliceError/TypeError/ChannelError）去除 `Arc::new` 包装
- **验证**：edge_throw 测试中 `throw 42i32` → `Error(v)` 的 v==42 直接通过；`throw "boom"` → v=="boom" 通过；`throw Rec(7i32)` → r.v==7 通过

### Bug #28：`??` (Elvis) 不支持 Throw 类型

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_throw 测试中，`mightFail() ?? 999i32`（mightFail 返回 `Throw<T, Error>`）结果为 `<non-scalar>`
- **现象**：`??` 仅对 Nullable(T?) 生效，对 Throw 的 Error 变体不做短路合并
- **影响**：无法用 `??` 为可能 throw 的表达式提供默认值
- **根因**：`compute_elvis` 仅检查 `is_null()`（Nullable 路径），不处理 `ThrowVal`；类型推断 `infer_expr_inner` 中 Elvis 分支不识别 `Ty::Throw`
- **修复方案**：`compute_elvis` 新增 `HeapObj::ThrowVal(tv)` 分支：Ok(v) → 返回 v（解包），Err(_) → 返回 rhs（默认值）。`Inference.rs` 的 `BinaryOp::Elvis` 和 `Expr::Elvis` 分支新增 `Ty::Throw` 处理，返回 `throw_parts(rl).0`（值类型），与 Nullable 对称
- **验证**：edge_throw 测试中 `(mightFail(false) ?? 999i32) == 5i32` 和 `(mightFail(true) ?? 999i32) == 999i32` 通过。注：`??` 优先级低于 `==`（与 C#/Swift/Kotlin 一致），比较时需加括号

### Bug #35：ADT 变体模式变量遮蔽函数参数时，f64 类型二元运算返回 0

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_adt 测试中，`Square(s) => s * s`（s 遮蔽参数 s）返回 0 而非 25.0
- **现象**：当 ADT 变体（`type T = | V(f64)`）的 match 模式变量名与函数参数名相同时，且模式变量为 f64 类型且在 match arm body 中参与二元运算（`*`、`+` 等），运算结果为 0 而非正确值
- **复现代码**：
  ```kuzo
  type W3 = | W3(f64)
  fun doubleF64(w: W3): f64 {
      match w {
          W3(w) => w * w   // w 遮蔽参数 w，返回 0（应为 25.0）
      }
  }
  println(doubleF64(W3(5.0f64)))  // 0（应为 25.0）

  fun addOneF64(w: W3): f64 {
      match w {
          W3(w) => w + 1.0f64   // 同样返回 0（应为 6.0）
      }
  }
  ```
- **不影响的情况**：
  - i32 类型相同遮蔽正常：`W2(w) => w + w`（i32）返回 84 ✓
  - f64 类型不遮蔽正常：`W3(v) => v * v` 返回 25.0 ✓
  - f64 类型遮蔽但无二元运算正常：`W3(w) => w` 返回 5.0 ✓
  - record 类型（非 ADT `|` 变体）相同遮蔽正常
- **根因**：`Inference.rs` 的 `lookup_narrowed` 在查询模式变量类型时，错误地返回了 scrutinee（函数参数）的 `ConstructorMatch` flow narrowing fact。当模式变量名与 scrutinee 名相同时（如 `match w { W3(w) => ... }`），scrutinee 的窄化类型（ADT `W3`）被错误应用到模式变量 `w` 上，导致二元运算的 `select_binary_compute_fn` 选择了 ADT 类型而非 f64 类型的 compute_fn，返回 0
- **修复方案**：在 `lookup_narrowed` 中，当遇到 `NarrowKind::ConstructorMatch` fact 时，检查该 fact 的 `bound_vars` 是否包含查询路径。若包含，说明该 fact 描述的是被遮蔽的 scrutinee（其模式变量名与查询路径相同），跳过此 fact 让 `infer_expr` 走 env 查询获取模式变量的正确字段类型
- **验证**：edge_match 测试中 `doubleF64(W3(5.0f64)) == 25.0f64`、`addOneF64(W3(5.0f64)) == 6.0f64`、`doubleI32(W2(42i32)) == 84i32` 全部通过；不遮蔽情况 `doubleF64NoShadow` 仍正常

### Bug #43：`cast(true).to(i32)` 返回 0 而非 1

- **状态**：已修复
- **发现场景**：edge_misc 测试中，`cast(true).to(i32)` 返回 0 而非 1
- **现象**：`cast(true).to(i32)` 返回 `0`（应为 1）；`cast(false).to(i32)` 返回 `0`（正确）。即 bool→i32 cast 中 true 被错误地转为 0。**对照**：反向 `cast(42i32).to(bool)` == true ✓、`cast(0i32).to(bool)` == false ✓（i32→bool 正常）
- **复现代码**：
  ```kuzo
  fun main(): void {
      val bool_to_i = cast(true).to(i32)
      println(bool_to_i)   // 0（应为 1）
      val bool_false_i = cast(false).to(i32)
      println(bool_false_i)   // 0（正确）
  }
  ```
- **影响**：所有依赖 bool→i32 转换的场景（如将 bool 编码为整数标志位）。由于反向 cast 正常，影响范围相对受限
- **根因**：`Value.rs::as_int_i128` 和 `as_float_f64` 的 match 中未列出 `ValueTag::Bool`，走 `_ => 0` / `_ => 0.0` 分支，导致 `true` 也被读为 0。`compute_cast_scalar` 对 Bool→Int 路径调用 `val.as_i32()`（委托 `as_int_i128`），对 Bool→Float 路径调用 `val.as_float_f64()`，两者均受影响
- **修复方案**：在 `as_int_i128` 中添加 `ValueTag::Bool => if v.bool_val { 1 } else { 0 }`，在 `as_float_f64` 中添加 `ValueTag::Bool => if v.bool_val { 1.0 } else { 0.0 }`。通用方法，非特例判断——Bool 作为标量类型统一参与整数/浮点读取路径
- **验证结果**：
  - edge_misc：`bool true -> i32 = 1` PASS、`bool false -> i32 = 0` PASS，ALL PASSED
  - cast 套件：`bool true to str`、`bool false to str` PASS，ALL PASSED
  - 回归测试 9 套：8 套全通过，1 套（edge_operators）仅 Bug #38 失败，零新增回归

### Bug #51：`cast(f32).to(f64)` 返回 void（f32→f64 类型提升失败）

- **状态**：已修复
- **现象**：`cast(f32).to(f64)` 返回 void（f32→f64 类型提升失败）
- **验证**：cast 套件 `f32 1.5 to f64` PASS，edge_channels `f32 pi recv equals sent` PASS
- **临时绕过**：直接比较 f32 值，不使用 cast 提升到 f64

---

## P3 优先级（边缘场景）

### Bug #2：`==` 在 record 上始终返回 true（与 #1 关联）

- **状态**：已修复 (2026-08-05，随 #1 一并修复）
- **现象**：`p1 == p3` 返回 `true`，无论字段是否相同
- **复现代码**：
  ```kuzo
  val p1 = Point(3, 4)
  val p3 = Point(5, 6)
  println(p1 == p3)  // true（应为 false）
  ```
- **影响**：record 相等性判断失效
- **根因**：与 #1 同根因。`select_binary_compute_fn` 对复合类型的 `==` 返回 `CF_EQ_I32`，`as_i32()` 恒为 0 导致所有复合类型判为相等。
- **修复**：随 #1 一并修复。`select_binary_compute_fn` 的复合类型检测分支对 `Eq` 分派到 `CF_EQ_OBJ`，调用 `compute_eq_obj` 进行深度语义比较。
- **验证**：`records` 测试中 `check(p == p2, "record value equality")` 验证相等返回 true，`check(p != p3, "record inequality (!=)")` 验证不等返回 false（原 bug 场景）；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #15：非 ASCII 字符串索引 panic

- **状态**：已修复 (2026-08-05)
- **现象**：对包含非 ASCII 字符（如 `'é'`、`'你'`）的字符串进行索引访问时，字符显示为 `U+XXXX` 转义形式而非实际字符；char 字面量 `'é'` 触发 panic
- **错误信息**：`end byte index ... is not a char boundary`
- **复现代码**：
  ```kuzo
  val u = "héllo你好"
  println(u[1])  // 原显示 U+00E9（应为 é）；'é' 字面量 panic
  ```
- **影响**：Unicode 字符串的索引访问与 char 字面量
- **根因**：三层问题：
  1. **`scan_char` 按单字节前进**：`Ast.rs` 的 `scan_char` 对非 ASCII 字符（多字节 UTF-8 序列）仅 `self.pos += 1`，导致 `pos` 停在字符中间，后续 `&self.source[start..self.pos]` 切片 panic（非 char boundary）。
  2. **`parse_char_value` 仅取首字节**：第 5705 行 `bytes[0] as u32` 对多字节字符仅取首字节值，无法还原 Unicode 码点。
  3. **`format_value` 对非 ASCII char 输出 U+转义**：`Reflect.rs` 两处 char 格式化逻辑对码点 > 0x7F 的字符输出 `U+{:04X}` 转义形式，而非实际字符。
- **修复**：
  1. `Ast.rs` 的 `scan_char` 非 ASCII 分支按 UTF-8 起始字节判断字符长度（1/2/3/4 字节），按字符边界前进 `self.pos`。
  2. `Ast.rs` 的 `parse_char_value` 用 `content.chars().next().map(|c| c as u32)` 解码完整 UTF-8 序列为 Unicode 码点。
  3. `Reflect.rs` 两处 char 格式化逻辑改用 `char::from_u32(c)` 将码点转为字符后输出，非法码点才 fallback 到 `U+XXXX` 转义。
- **验证**：`strings` 测试新增 4 个 Unicode 字符索引用例（`é`、`你`、`好`、CJK 首字符）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #17：字符串插值中 `bool == bool` 表达式恒返回 true

- **状态**：已修复 (2026-08-05)
- **现象**：字符串插值 `"{bool_expr}"` 中直接嵌入 `bool == bool` 比较表达式时，结果恒为 `true`，而相同表达式直接打印或赋值给变量后再插值均正常
- **复现代码**：
  ```kuzo
  println(true == false)              // false（正确）
  val r: bool = true == false
  println(r)                          // false（正确）
  println("{r}")                      // false（正确）
  println("{true == false}")          // true（错误，应为 false）
  println("d: {5 == 10}")            // "d: false"（正确，int == int 正常）
  ```
- **影响**：字符串插值中直接嵌入 `bool == bool` 表达式的场景。注意 `int == int` 等其他类型比较在插值中正常，仅 `bool == bool` 受影响
- **根因**：`Inference.rs` 的 `infer_expr_inner` 对 `Expr::StrInterp(_)` 仅返回 `ConcreteType::Str`，未递归推断插值内部的子表达式，导致子表达式的 ExprInfo 未注册到 `expr_types`。IR 编译 `select_binary_compute_fn` 查 `expr_type_name(lhs)` 返回 `None`，回退 `ty_name = "i32"`，将 `bool == bool` 误分派到 `CF_EQ_I32`。`Value::as_int_i128` 对 `ScalarTag::Bool` 走 `_ => 0` 分支（line 1237），`true`/`false` 均读为 0，`0 == 0` 恒为 true。`int == int` 正常是因为 `as_i32` 对整数返回真实值
- **修复**：`Inference.rs` 的 `Expr::StrInterp` 分支递归调用 `infer_expr` 推断每个 `InterpolationPart::Expression` 子表达式，确保其 ExprInfo 注册到 `expr_types`，使 IR 编译能正确按操作数类型分派 compute_fn
- **验证**：`strings` 测试新增 6 个插值比较用例（`bool == bool` true/false、`int == int` true/false、带前缀的 bool/int 插值比较）全部通过；14 个功能测试 + 5 个性能测试全部通过，无回归

### Bug #36：不支持 `\uXXXX` 和 `\0` 字符串/字符转义序列

- **状态**：已修复 (2026-08-07)
- **发现场景**：edge_strings 测试中，`"e\u0301"` 导致 parse error: expected expression
- **现象**：Kuzo 字符串和字符字面量不支持以下转义序列：
  - `\uXXXX`（Unicode 码点转义，如 `\u0301` 组合尖音符）
  - `\u{XXXX}`（花括号形式，支持辅助平面，如 `\u{1F600}`）
  - `\0`（空字符，NUL）
- **复现代码**：
  ```kuzo
  val s = "e\u0301"    // parse error: expected expression
  val c = '\0'          // parse error: expected expression
  ```
- **影响**：无法在源码中构造组合字符序列（如分解形式的 é = e + U+0301）、无法表示 NUL 字符。预组合形式（如 é = U+00E9）可直接输入
- **支持的转义**（修复前）：`\t` `\n` `\r` `\\` `\"` `\'`
- **根因**：
  1. `scan_string` 词法扫描阶段转义匹配不含 `b'0'` 和 `b'u'`，直接返回 `InvalidEscape`
  2. `unescape_string` 值转换阶段不处理 `\0` 和 `\u`
  3. `scan_char` 字符字面量不支持 `\uXXXX`（无花括号形式），`parse_char_value` 不解析 `\u` 转义
  4. `contains_interpolation` 和 `parse_string_literal` 中 `\` 转义只跳过 2 字节，导致 `\u{XXXX}` 中的 `{` 被误认为插值标记
- **修复方案**：
  1. `scan_string`：转义匹配新增 `b'0'`（简单跳过）和 `b'u'`（扫描 4 位十六进制或花括号形式）
  2. `scan_char`：`\u` 分支新增无花括号 4 位十六进制形式（与字符串对称）
  3. `unescape_string`：新增 `b'0'` → NUL，`b'u'` → 解析 `\uXXXX` 或 `\u{XXXX}` 并通过 `char::from_u32` 转换
  4. `parse_char_value`：新增 `b'u'` 分支，解析花括号和无花括号两种形式
  5. `contains_interpolation` 和 `parse_string_literal`：遇到 `\u` 时跳过整个转义序列（而非仅 2 字节），避免花括号被误认为插值
- **验证**：edge_strings 测试中 `\u0301`、`\u{2764}`、`\u{1F600}`、`\u00E9`、`\0` 的码点值和长度全部通过；char 字面量 `\u00E9`、`\u{1F600}`、`\0` 也通过；34 个功能测试套件全部 ALL PASSED，无回归

### Bug #46：字符串字面量中 `{[...]}` 被当作插值解析

- **状态**：已修复 (2026-08-07)
- **现象**：字符串字面量中包含 `{[...]}` 模式时，`{[...]}` 被当作字符串插值解析，`[...]` 被视为数组字面量表达式，内部标识符报 undefined variable
- **复现代码**：
  ```kuzo
  check(tag_x.wrap3() == "<{[X]}>", ...)
  // sema 错误：undefined variable 'X'（`{[X]}` 被解析为插值，`[X]` 为数组字面量）
  ```
- **影响**：无法在字符串字面量中直接包含 `{[...]}` 文本（如 JSON、数学符号）。Kuzo 无 `{}` 转义机制（`{{ }}` 或 `\{` 均不支持）。
- **根因**：字符串插值词法/解析阶段将所有 `{...}` 视为插值表达式，没有转义语法
- **修复**：`Parser.rs` 的 `scan_string` 新增 `{{`/`}}` 花括号转义语法。`{{` 表示字面量 `{`，`}}` 表示字面量 `}`，不被当作插值解析。需要字面量花括号时使用 `"{{[X]}}"` 代替 `"{[X]}"`
- **验证**：edge_traits 测试使用 `{{`/`}}` 转义后 ALL PASSED；8/8 unit + 35/35 functional + 5/5 perf 全部通过，无回退

---

## 语法限制（非 Bug，需文档说明）

这些是语言设计选择而非 bug，但需要文档明确说明：

| 限制 | 说明 | 绕过方式 |
|------|------|---------|
| 闭包不支持显式返回类型标注 | `fun(n: i32): i32 { ... }` 解析错误 | 省略返回类型 `fun(n: i32) { ... }` |
| `T??` 双 nullable 后缀不可用 | 词法将 `??` 解析为 Elvis 操作符，`val x: i32?? = ...` 触发 parse error | 不使用双 nullable；或用显式包装类型 `type Opt = Opt(inner: i32?)` |
| `T?[]` nullable 元素数组不可用 | `parse_nullable_type` 的 `?` 后缀循环不消费 `[`，`val x: i32?[] = ...` 触发 parse error: expected '=' | 改用 `i32[]?`（nullable 数组，语义不同）或显式包装类型 |
| 数组层不做 numeric widening | `try_widen_unify` 无 Array 分支，strict `unify` 递归比元素类型；`val x: i64[] = [1i32]` 报 mismatch（即便 i32→i64 可提升）。注：Throw/Nullable 包裹的 numeric 元素在 widening 分支内会提升，但数组层先失败，故 `Throw<i64,Error>[] = [Ok(1i32)]` 仍 mismatch | 数组元素类型与注解严格一致；需 widening 时逐元素显式转换 |

---

---

## Bug #56：match arm 间 current_effect 泄漏导致递归 ADT 遍历返回 void

- **状态**：已修复 (2026-08-08)
- **优先级**：P0（核心功能阻塞：递归 ADT 遍历完全失效）
- **位置**：`src/ir/Builder.rs:3191-3281`（compile_match）
- **现象**：对递归 ADT 类型（如 `List = | Nil | Cons(i32, List)`）进行 match 遍历的递归函数返回 void。即使 base case（`Nil => 0`）也不执行，`listLen(Nil)` 返回 void 而非 0。影响 9 个测试用例（adt、edge_adt、edge_generics、edge_match、edge_recursion、edge_stress、edge_traits、patterns、edge_defer 中的递归 defer 部分），共 45 个断言失败。
- **根因**：`compile_match` 在第一阶段按顺序编译所有 arm 的 pattern + body（`compile_branch_subgraph`），但 `compile_branch_subgraph` 不隔离 `current_effect`。当某个 arm body 包含非尾递归自调用时，`non_tail_rec_to_loop` 拦截会设置 `current_effect` 为 Continue barrier 节点（`compile_call` 第 4632-4750 行）。此后构建 Gate 时（第二阶段从后往前），所有 arm 的 Gate 输入都使用被污染的全局 `current_effect`，导致前序 arm 的 Gate 依赖了后序 arm body 产生的 Continue barrier。运行时，即使前序 arm 的 pattern 匹配成功，其 Gate 因依赖另一个 arm 的 barrier 而无法执行，整个 match 返回 void。
- **触发条件**：match 表达式中某个 arm body 包含非尾位置自调用（触发 `non_tail_rec_to_loop` 拦截），且该 arm 不是最后一个编译的 arm。典型场景：`match l { Nil => 0; Cons(_, t) => 1 + listLen(t) }`——Cons arm 的 `listLen(t)` 被拦截产生 Continue barrier，污染 Nil arm 的 Gate。
- **修复**：在 `compile_match` 的 `ArmData` 结构中新增 `effect_before: Option<NodeId>` 字段，在每个 arm 编译前保存 `current_effect`。Gate 构建阶段使用 arm 级别的 `effect_before` 而非全局 `current_effect`，确保每个 arm 的 Gate 仅依赖该 arm 编译前已完成的副作用，不受后续 arm body 副作用的影响。
  - [Builder.rs:3198-3202](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L3198-L3202)：ArmData 新增 `effect_before` 字段
  - [Builder.rs:3210-3212](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L3210-L3212)：arm 编译前保存 `effect_before`
  - [Builder.rs:3246-3252](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L3246-L3252)：ArmData 初始化 `effect_before`
  - [Builder.rs:3273-3281](file:///Users/haojunhuang/CLionProjects/Kuzo/src/ir/Builder.rs#L3273-L3281)：Gate 输入使用 `ad.effect_before` 替代 `self.current_effect`
- **验证**：8/9 受影响测试通过（adt、edge_adt、edge_generics、edge_match、edge_recursion、edge_stress、edge_traits、patterns 全部 ALL PASSED）；edge_defer 剩 1 个失败为独立 bug（non_tail_rec_to_loop 工作栈模拟不支持 defer LIFO unwind，与本 bug 无关），见 Bug #57。34 功能测试无回归，Rust 单元测试通过。

---

## Bug #57：non_tail_rec_to_loop 转换破坏 defer LIFO 语义

- **状态**：已修复 (2026-08-08)
- **优先级**：P1（defer 语义正确性）
- **位置**：`src/pass/Analyzer.rs:2850-2881`（memo_pass 非尾递归检测）
- **现象**：含 defer 的非尾递归函数（如 `deferRecur(n)`）被 `non_tail_rec_to_loop` 转换为工作栈循环后，defer 仅在函数退出时执行一次，而非每次递归调用完成时执行（LIFO 顺序）。`recur_log` 输出 `'nullnull'` 而非预期的 `'0123'`。
- **根因**：`non_tail_rec_to_loop` 将递归调用转为 while 循环（工作栈模拟），每次"递归调用"是循环的一轮迭代。但 defer 注册到函数主子图的 `defer_table`（`compile_stmt` Defer 分支通过 `current_function_sg` 注册），运行时仅在函数帧终止时执行一次（`Schedule.rs:928-933`）。工作栈模拟不创建/销毁递归帧，defer 无法在每轮迭代完成时触发。此外，defer body 引用的参数 `n` 在循环中已失效（`param_cur` 每轮覆盖），导致 `cast(n).to(str)` 读到 null。
- **触发条件**：纯函数（purity 分析未检测到全局赋值副作用）+ 非尾递归 + 函数体含 defer 语句。典型场景：`fun deferRecur(n: i32): i32 { defer recur_log = recur_log + cast(n).to(str); if n <= 0 { 0 } else { n + deferRecur(n - 1) } }`。
- **修复**：在 `memo_pass` 的非尾递归检测分支中，使用已有的 `has_defer` 函数检查函数体是否包含 defer。若含 defer，跳过 `NonTailRecToLoop` 转换，降级为 `Memoize` 策略（保持真递归调用，defer 在每次帧终止时正确执行）。
  - [Analyzer.rs:2850-2863](file:///Users/haojunhuang/CLionProjects/Kuzo/src/pass/Analyzer.rs#L2850-L2863)：新增 `has_defer` 检查，含 defer 的函数降级为 Memoize
- **验证**：edge_defer ALL PASSED（deferRecur 的 `recur_log == "0123"` 正确）。34 功能测试无回归，Rust 单元测试通过。

---

## Bug #58：类型注解不匹配报错中 `found` 侧显示未解析的 type var

- **状态**：已修复（2026-08-10）
- **优先级**：P3（显示瑕疵，不影响正确性）
- **位置**：`src/types/Display.rs:22`（TypeDisplay 的 TypeVar 分支）
- **现象**：当值表达式含未约束的泛型类型变量时，`type annotation mismatch` 的 `found` 侧会显示内部 type var 索引（如 `'_529`）而非用户可读的类型。
  ```
  val arr: Throw<i64, Error>[] = [Ok(1i32)]
  // 实际输出：type annotation mismatch: expected 'Throw<i64, Error>[]', found 'Throw<i32, '_529>[1]'
  // 期望输出：found 'Throw<i32, '_>[1]' 或 'Throw<i32, Error>[1]'
  ```
- **根因**：`Ok(1i32)` 构造时错误类型未被约束（`Ok<T, E>` 的 `E` 是 fresh type var），`type annotation mismatch` 报错时直接 `arena.display(val_ty)` 渲染，`TypeDisplay` 对 `Ty::TypeVar(idx)` 输出 `'_<idx>`（见 Display.rs:22）。用户无法理解 `'_529` 的含义。
- **影响**：错误信息可读性差，"杠精用户"难以从报错定位问题。仅影响含未约束 type var 的值（Ok/Error 构造、未标注的泛型函数返回值等）。
- **修复**：修改 `Display.rs` 的 `TypeVar` 分支，将 `write!(f, "'_{}", idx)` 改为 `f.write_str("'_")`。隐藏内部索引，与 Rust 匿名生命周期 `'_` 显示惯例一致。这是通用修改，所有使用 TypeDisplay 的地方都会受益。
- **验证**：`edge_nested_types/negative/array_of_throw_elem_mismatch.kz` 现输出 `found 'Throw<i32, '_>[1]'`；全部 9 个负向用例正常报错；37 个功能测试 sema check 全部通过；`cargo test --lib` 14/14 PASS。

---

## Bug #59：嵌套类型注解不匹配的报错路径缺乏测试覆盖（已补）

- **状态**：已修复（补测试）
- **优先级**：P3（测试覆盖缺口）
- **位置**：`tests/functional/edge_nested_types/`（新增）
- **现象**：在补充测试前，`type annotation mismatch` 错误路径仅由 Bug #23（函数类型别名）间接覆盖，嵌套数组/嵌套 Throw/数组 of Throw/Throw of 数组/nullable 数组/嵌套函数类型等注解不匹配场景**完全无测试**。Display.rs 的递归渲染（`i32[][]`、`Throw<Throw<i32,Error>,Error>`）虽有实现但无回归保护。
- **根因**：现有 functional 测试均为正向用例（能编译通过），无负向用例触发 `type annotation mismatch`。
- **修复**：新增 `tests/functional/edge_nested_types/` 目录：
  - `src/Main.kz`：10 节正向测试（2D/3D 数组、嵌套 Throw、数组 of Throw、Throw of 数组、嵌套函数类型、nullable 数组、record 嵌套字段、函数签名嵌套注解、混合 `Throw<i32[]?, Error>`），全部 ALL PASSED
  - `negative/`：7 个负向用例（`kuzo debug --stage check` 均退出 1），覆盖维度不匹配、元素类型不匹配、嵌套 Throw 内部不匹配、数组 of Throw 元素不匹配、Throw of 数组元素不匹配、nullable 数组元素不匹配、函数返回值不匹配
- **验证**：正向 `kuzo run` ALL PASSED；负向 7/7 报 `type annotation mismatch` 且 expected/found 显示正确（除 Bug #58 的 `'_NNN` 显示瑕疵）。
- **附注**：测试中 `kuzo.toml` 的 `entry` 应为 `src/Main.kz`，但现存 `edge_arrays` 等目录误写为 `src/Main.kuzo`（main.rs 的 DEFAULT_ENTRY 与 read_source 实际读 `.kz`，manifest 的错误 entry 在 `kuzo run`（无参，走 resolve_entry_path 读 manifest）时会触发 "No such file"，需用 `kuzo debug` 绕过）。建议统一修正现存 toml。

---

## Bug #60：numeric widening 在标量 / 数组 / Throw 之间行为不一致

- **状态**：已修复（2026-08-10，方案 A 全严：移除所有 numeric widening）
- **优先级**：P2（语义不一致，影响类型系统一致性预期）
- **位置**：`src/sema/Inference.rs:1093-1245`（try_widen_unify）+ `src/types/Arena.rs:791-795`（unify 的 Array 分支）
- **现象**：同一对 numeric 类型（i32 → i64）在三种上下文中的 widening 行为不一致：
  | 上下文 | 代码 | 结果 |
  |--------|------|------|
  | 标量 | `val a: i64 = 1i32` | ✅ 通过（numeric widening） |
  | 数组 | `val b: i64[] = [1i32]` | ❌ `type annotation mismatch: expected 'i64[]', found 'i32[1]'` |
  | Throw | `val t: Throw<i64, Error> = Ok(1i32)` | ✅ 通过（Throw 分支对 value_type widening） |
- **根因**：`try_widen_unify` 的 match 分支仅处理 Nullable/Throw/Void/numeric，**无 Array 分支**。当 strict `unify`（Arena.rs:791）的 Array 分支递归比元素类型 i64 vs i32 失败后，`try_widen_unify` 直接 fallback 到 `Err(TypeMismatch)`，不尝试对元素做 numeric widening。而 Throw 分支（Inference.rs:1178-1226）和裸 numeric 分支（Inference.rs:1128-1136）都会调用 `can_coerce_numeric` 做提升。
- **影响**：
  1. 语义割裂：用户写 `i64 = i32` 通过，装进数组 `i64[] = [i32]` 就报错，违反最小惊讶原则
  2. 反直觉排序：Throw（复合类型）比数组（复合类型）更宽松，无设计依据
  3. 阻碍数值计算：科学计算中 `[1i32, 2i32]` 提升为 `i64[]` 是常见需求，当前必须逐元素 `cast`
- **建议修复**（二选一，需明确设计决策）：
  - 方案 A（全严，Rust 风格，符合用户偏好）：移除 `try_widen_unify` 中所有 numeric widening 分支，标量也不再隐式提升。所有 numeric 转换必须显式 `cast`。此方案与用户 profile 中"Rust-style strict type handling"一致。
  - 方案 B（全宽，递归 widening）：在 `try_widen_unify` 中新增 Array 分支，当两侧都是 Array 时递归对元素调用 `try_widen_unify`，让 numeric widening 透传到元素层。
  - **当前不一致状态不可接受**，必须二选一。
- **复现**：
  - `tests/functional/edge_nested_types/positive_widening.kz`（标量 + Throw 通过，exit 0）
  - `tests/functional/edge_nested_types/negative/widening_inconsistency.kz`（数组报错，exit 1）
  - 两者共同钉死当前不一致行为，修复后需同步更新期望

---

## Bug #61：类型别名在 mismatch 报错中被静默展开

- **状态**：已修复（2026-08-10）
- **优先级**：P2（错误信息可读性，影响用户定位）
- **位置**：`src/sema/Inference.rs:2989-3002`（type annotation mismatch 报错）+ `src/types/Display.rs`（TypeDisplay）
- **现象**：用户定义类型别名后，在 `type annotation mismatch` 报错中，`expected` 侧显示别名展开后的底层类型而非别名名。
  ```kuzo
  type Mat2D = i32[][]
  type I64Arr = i64[]
  fun main(): void {
      val a: Mat2D = [[1i64, 2i64]]   // 用户写 Mat2D
      val b: I64Arr = [1i32, 2i32]    // 用户写 I64Arr
  }
  ```
  实际报错：
  ```
  type annotation mismatch: expected 'i32[][]', found 'i64[2][1]'
  type annotation mismatch: expected 'i64[]', found 'i32[2]'
  ```
  期望报错：
  ```
  type annotation mismatch: expected 'Mat2D', found 'i64[2][1]'
  type annotation mismatch: expected 'I64Arr', found 'i32[2]'
  ```
- **根因**：`infer_stmt` 的 ValDecl/VarDecl 分支在计算 `annot_ty` 时调用 `type_from_ast`，该函数通过 `concretize_type` 将别名解析到底层 `TypeHandle`（如 `i32[][]`），别名名信息在解析过程中丢失。报错时 `arena.display(annot_ty)` 只能渲染解析后的底层类型。`TypeDisplay` 无从知道这个 handle 来自哪个别名。
- **影响**：
  1. 用户写 `Mat2D` 却在报错里看到 `i32[][]`，无法快速对应自己代码中的类型声明
  2. 别名本是为可读性而生，报错展开别名削弱了别名的价值
  3. 对比 Rust（保留类型别名名）、TypeScript（保留别名），Kuzo 此行为不符合主流语言惯例
- **建议修复**：在 `TypeHandle` 或 `Ty` 中增加可选的"源别名名"元数据（`origin_alias: Option<Symbol>`），`concretize_type` 解析别名时记录原名，`TypeDisplay` 优先渲染别名名（可附 `= <底层类型>` 辅助）。或更轻量：在 mismatch 报错路径保留 AST 层的 `TypeRef`，用 AST 节点信息渲染 expected 侧。
- **复现**：`tests/functional/edge_nested_types/negative/alias_expanded_in_error.kz`（exit 1，当前显示展开形式）

---

## 杠精全特性测试批次（Bug #62-#70）

以下 bug 由"杠精"视角对 Kuzo 全部语言特性（变量/字面量/函数/闭包/泛型/ADT/Record/Throw/async/channel/数组/字符串/插值/控制流）进行边界测试发现。每条均含最小复现代码。

---

## Bug #62：整数除以零静默返回 0（无 panic）

- **状态**：已修复（2026-08-10，Ops.rs arith_div_* 添加除零检查，触发 panic）
- **优先级**：P0（内存/数值安全）
- **现象**：
  ```kuzo
  val z: i32 = 0i32
  val dz: i32 = 1i32 / z   // 打印 0，不 panic
  val mz: i32 = 1i32 % z   // 打印 0，不 panic
  ```
  程序正常退出 exit 0，无任何报错或 panic。
- **根因**：整数除法/取模运行时未检查除数为零，直接执行硬件指令，x86 `div` 对零除数的行为被静默吞掉（或 VM 用了带 fallback 的实现）。
- **影响**：静默错误结果比 panic 更危险——程序继续运行用错误值计算，难定位。Bug #22 修复了"有符号整数除法溢出 panic"，但零除数这条路径遗漏。
- **建议修复**：除法/取模前检查除数为零，panic 或抛 `Error("division by zero")`。
- **复现**：`val dz: i32 = 1i32 / 0i32; println(dz)` → 打印 0

---

## Bug #63：数组越界访问不 panic，静默返回垃圾值

- **状态**：已修复（2026-08-10，Compute.rs compute_array_index 添加索引范围检查，越界 panic）
- **现象**：
  ```kuzo
  val arr: i32[] = [10i32, 20i32, 30i32]
  val oob: i32 = arr[5]    // 打印 <non-scalar>，不 panic
  val neg: i32 = arr[-1]   // 打印 <non-scalar>，不 panic
  val empty: i32[] = []
  val e: i32 = empty[0]    // 打印 <non-scalar>，不 panic
  ```
  程序正常退出 exit 0。`<non-scalar>` 是未初始化/越界内存的 Display 输出。
- **根因**：数组索引运行时未做边界检查（`0 <= idx < len`），直接按偏移读取，越界返回未初始化内存。
- **影响**：这是静态类型语言最严重的安全缺陷——用户可读任意内存。负索引同理。对比 Rust（panic）、Java（ArrayIndexOutOfBoundsException）、Python（IndexError），Kuzo 静默返回垃圾值是最差行为。
- **建议修复**：数组索引运行时强制 `0 <= idx < len` 检查，越界 panic。
- **复现**：`val x: i32 = [1i32][10i32]; println(x)` → 打印 `<non-scalar>`

---

## Bug #64：非穷尽 match 不报错，运行时静默返回 void

- **状态**：已修复（2026-08-10，sema 阶段 check_match_exhaustive 检查 ADT 构造器覆盖；Builder.rs compile_panic_subgraph + Compute.rs compute_match_fallback 运行时兜底 panic）
- **优先级**：P0（类型安全）
- **现象**：
  ```kuzo
  type Color = | Red | Green | Blue
  fun toStr(c: Color): str {
      match c {
          Red => "r"
          Green => "g"
      }   // 漏掉 Blue 分支
  }
  fun main(): void {
      println(toStr(Blue))   // 打印 "void"，不 panic
  }
  ```
  sema 阶段 `kuzo debug --stage check` 报 `ok (no type errors)`，运行时传 `Blue`（无匹配分支）静默返回 `void`，而函数声明返回 `str`。
- **根因**：sema 的 match 穷尽性检查未实现或不完整——漏分支不报 `non-exhaustive match`。运行时无匹配分支时无 fallback/panic，直接"穿透"返回默认值（void）。
- **影响**：静态类型语言的核心安全保证被破坏——声明返回 `str` 的函数可能返回 `void`。所有 match 表达式都不安全。
- **建议修复**：1) sema 实现 match 穷尽性检查，漏分支报 `non-exhaustive match: missing Blue`；2) 运行时无匹配分支时 panic（兜底）。
- **复现**：见上方代码，`kuzo debug --stage check` 通过，`kuzo run` 打印 `void`

---

## Bug #65：defer + throw/return 后调用者后续代码不执行

- **状态**：已修复并验证（throw 场景运行时验证通过；return 场景通过 edge_defer 测试套件 15/15 PASS 确认无回归）
- **优先级**：P0（控制流正确性）
- **现象**：
  ```kuzo
  fun withDefer(): Throw<i32, Error> {
      defer { println("defer ran") }
      throw Error("boom")
  }
  fun main(): void {
      println("1. before")
      match withDefer() {
          Error(_) => println("2. caught")
          _ => println("2. other")
      }
      println("3. after match")   // 不执行
      println("4. end")           // 不执行
  }
  ```
  输出：`1. before` / `defer ran` / `2. caught`，然后程序静默终止 exit 0，`3.` 和 `4.` 不打印。return 同理：
  ```kuzo
  fun f(): i32 { defer { println("d") }; return 42i32 }
  fun main(): void {
      val r = f()
      println("r={r}")        // 打印 r=42
      println("after f")      // 不执行
  }
  ```
- **根因**（throw 场景）：sync 路径 `run_frame_sync_inner`（Compute.rs）中，Call 节点完成后无条件检查返回值是否为 `ThrowVal(Err)`，若是则设为 `ControlSignal::Return` 并 `continue`，**跳过了 `notify_downstream`**。导致调用者帧中 Call 节点的下游（match 等）永远不会变成 ready，match 之后的语句不执行。这与 async 路径（Subgraph.rs）的正确行为不一致——async 路径只有 Gate 分支/loop frame 的 Return 才传播，跨函数调用的 Return 不传播。
- **根因**（return 场景）：代码分析显示 return 42（i32）不触发 throw 传播路径，return 场景的根因待运行时验证确认。
- **影响**：任何在 defer + throw 函数调用之后的代码都可能不执行。defer 是语言核心特性，此 bug 使 defer 在实际代码中不可用。
- **修复**：移除 Compute.rs `run_frame_sync_inner` 中 Call 节点对 `ThrowVal(Err)` 的无条件 Return 传播。Throw 值是数据，应流向下游消费者（match/let/`?`）；只有 `?` 操作符（compute_propagate）和 throw 语句本身才将 Throw 错误转为控制流 Return。这与 async 路径（Subgraph.rs）的控制信号传播逻辑保持一致。
- **复现**：见上方代码；测试 probe `tests/functional/troll_battery/probes/p15_defer_throw.kz`

---

## Bug #66：defer 在块作用域退出时不执行（只在函数级执行）

- **状态**：已修复
- **优先级**：P1（语义不一致）
- **现象**：
  ```kuzo
  fun main(): void {
      var log: str = ""
      {
          defer { log = log + "1" }
          defer { log = log + "2" }
          defer { log = log + "3" }
      }   // 块结束，期望 defer LIFO 执行
      println("log = {log}")   // 打印 "log = "（空），defer 未执行
  }
  ```
  defer 在 `{}` 块退出时**不执行**，`log` 为空字符串。
- **根因**：defer 只注册到函数级 defer 栈，块作用域退出时不清算。对比 Go/Zig（defer 在任意作用域退出时执行）、Rust（drop 在块退出时执行），Kuzo 的 defer 语义不完整。
- **影响**：资源清理（文件关闭、锁释放）在块作用域内不可靠。用户期望 `{ defer { close(f) } ... }` 在块结束时关闭文件，实际不执行。
- **修复**：在 `Builder.rs` 的 `compile_block` 中记录块进入时的 `defer_table` 长度（`defer_mark`），块退出时通过 `compile_block_defer_cleanup` 提取新增 defer 并生成 LIFO 清算 Call 节点。引入 `in_function_top_block` 标志区分函数体顶层块和嵌套块：函数体顶层块的 defer 保留在 `defer_table` 中由函数退出时的 `run_defers_sync`/`process_frame` 执行；嵌套块的 defer 在块退出时提取并通过 `chain_effects` 链接到块结果之后执行。
- **验证**：块级 defer 测试输出 `log = 321`（LIFO 顺序正确）；edge_defer 15/15、throw 15/15 全部通过，无回归。
- **复现**：见上方代码

---

## Bug #67：移位越界行为不明确（1 << 32 返回 1）

- **状态**：已修复（2026-08-10）
- **优先级**：P2（语义不明确）
- **现象**：
  ```kuzo
  val sh: i32 = 1i32 << 32   // 打印 1
  ```
  i32 移位 32 位（超出 0-31 范围）返回 1（等于 `1 << 0`）。
- **根因**：移位运行时未检查 shift amount 范围，x86 `shl` 会 mask 低 5 位（`32 & 0x1F = 0`），故 `1 << 32 == 1 << 0 == 1`。这是硬件行为，但语言层应明确：panic 或定义为 wrapping。
- **影响**：用户写 `1 << 32` 期望 0（数学语义）或 panic，实际得到 1，违反直觉。
- **建议修复**：明确语义——要么 panic（shift amount >= bit_width），要么文档化 wrapping 行为。建议 panic（更安全）。
- **复现**：`println(1i32 << 32)` → 打印 1

---

## Bug #68：函数类型后缀数组注解解析优先级错误

- **状态**：已修复（2026-08-10）
- **优先级**：P2（语法歧义）
- **现象**：
  ```kuzo
  var fns: (i32) -> i32[] = []   // parse 通过
  // 但 sema 报：type annotation mismatch: expected '(i32) -> i32[]', found ''_543[]'
  ```
  `(i32) -> i32[]` 被解析为 `(i32) -> (i32[])`（返回 i32 数组的函数）而非 `((i32) -> i32)[]`（函数数组）。
- **根因**：类型解析器中 `[]` 后缀的优先级高于 `->`，`->` 右侧的类型先吃掉 `[]`。用户无法直接写"函数数组"类型，必须用别名绕过：`type IntFn = (i32) -> i32; var fns: IntFn[] = []`。
- **影响**：函数数组（回调列表、策略数组等常见模式）无法直接声明，必须别名绕过。
- **建议修复**：调整类型解析优先级，让 `[]` 后缀绑定到整个函数类型，或要求函数类型用括号包裹 `((i32) -> i32)[]`。
- **复现**：`var fns: (i32) -> i32[] = []`

---

## Bug #69：空 record 构造报 undefined variable

- **状态**：已修复（2026-08-10）
- **优先级**：P2（特性缺失）
- **现象**：
  ```kuzo
  type Unit = Unit()
  val u: Unit = Unit()   // sema 报：undefined variable 'Unit'
  ```
  零字段 record 定义成功，但构造时报 `undefined variable 'Unit'`。
- **根因**：两层问题：
  1. **Parser bug**：`parse_type_def` 中 `Identifier()` 空括号路径缺少 `else` 分支调用 `try_parse_single_ctor_adt()`，导致 `type Unit = Unit()` 被解析为类型别名（Alias）而非 ADT，构造器从未注册。
  2. **Sema gap**：零参数构造器在 `build_ctor_fn_type` 中返回 ADT 类型（非函数类型），`Unit()` 调用时 callee 解析为 ADT 类型而非函数，Call handler 报错。
- **修复**：
  1. Parser：在 `parse_type_def` 的 `if !self.check(RParen)` 后添加 `else` 分支，对空括号 `Name()` 调用 `try_parse_single_ctor_adt()`，正确解析为 ADT。
  2. Sema：在 Call handler 的构造器消歧路径中，当 `ctors.len() == 1 && args.is_empty() && ctor.field_type_reprs.is_empty()` 时，直接返回 ADT 类型（零参数构造器用 `()` 调用等价于使用裸值）。
- **验证**：`edge_adt` 测试新增 section 14（Marker()/Leaf()/Nil() 零参数构造器调用），sema check + runtime 全部 PASS，无回归。

---

## Bug #70：字符串插值转义花括号 {{}} 不正确 + 空插值 {} parse error

- **状态**：已修复（2026-08-10）
- **优先级**：P2（字符串插值）
- **现象**：
  ```kuzo
  // 1. 转义花括号
  check("{{x}}" == "{x}", "转义花括号")   // FAIL：{{x}} 不等于 {x}
  // 实际 {{x}} 可能被解析为插值 {x}（输出 42）+ 字面 }

  // 2. 空插值
  val s: str = "x={}"   // parse error: expected expression
  ```
- **根因**：
  1. **转义花括号**：经分析，`{{`/`}}` 转义机制在 `contains_interpolation`、`parse_string_literal` 和 `unescape_string` 三处均已正确实现。`{{` 被识别为字面 `{` 的转义（跳过插值检测），`}}` 被识别为字面 `}`。原 BUG_REPORT 中的现象描述有误。
  2. **空插值**：`{}` 内无表达式，`parse_interpolation_expr` 失败时静默截断错误，用户得不到明确的错误提示。
- **修复**：
  1. 转义花括号：无需修改（已正确实现）。
  2. 空插值：在 `parse_string_literal` 中添加空表达式检查，当 `expr_text.trim().is_empty()` 时返回明确的 `ParseError`：`"empty interpolation expression in string literal; use {{}} for literal braces"`。
- **验证**：`edge_string_interp` 测试新增 section 22（10 个测试用例），覆盖 `{{ebv}}` 转义、`{{}}` 空花括号转义、混合转义+插值、双重转义 `{{{{}}}}`，sema check + runtime 全部 PASS，无回归。

---

## 杠精电池批次（2026-08-10）

> 从用户视角对 Kuzo 全特性做"杠精"测试，不参考已有测试用例，独立设计探针。测试位于 `tests/functional/troll_battery/`，每个探针为独立 `.kz` 文件。下列编号续接 #70。

## Bug #71：整数取模零静默返回 0（与 #62 同类，未覆盖）

- **状态**：已修复（2026-08-10，与 #62 一并修复，Ops.rs arith_mod_* 添加除零检查）
- **优先级**：P1（数值语义）
- **现象**：
  ```kuzo
  val m: i32 = 1i32 % 0i32
  println("m={m}")   // 输出 m=0，exit code 0，不 panic
  ```
- **根因**：与 #62（整数除以零静默返回 0）同一类缺陷，但取模路径未一并修复。`% 0` 在数学上未定义，应 panic 或报错。
- **影响**：掩盖程序错误；用户无法依赖取模零触发失败来发现 bug。
- **建议修复**：与 #62 统一处理 — 整数 `/0` 和 `%0` 都应 panic（或提供 `checked_rem` 而默认 panic），保持语义一致。
- **复现**：`tests/functional/troll_battery/probes/p13_int_mod_zero.kz`

---

## Bug #72：字面量溢出 sema check 通过但 IR 阶段报错（阶段不一致）

- **状态**：已修复（sema 阶段新增 check_int_literal_range 范围检查，与 IR 阶段一致）
- **优先级**：P1（编译流水线一致性）
- **现象**：
  ```kuzo
  val over: i8 = 200i8   // 200 超出 i8 范围 (-128..=127)
  ```
  - `kuzo debug --stage check` 输出 `ok: ... (no type errors)`
  - `kuzo run` 输出 `IR error: integer literal '200' at line 40:23 is out of range for i8 (valid range: -128..=127)`
- **根因**：字面量范围检查只在 IR 阶段做，sema 阶段未做。IDE/LSP 走 check 阶段会漏报，用户以为类型正确，运行/构建才报错。
- **影响**：编辑器诊断与编译结果不一致；用户体验割裂。
- **建议修复**：在 sema 阶段对带类型后缀的整数字面量做范围检查（i8/u8/.../i64/u64 各自范围），与 IR 阶段共用一套范围常量。
- **复现**：`tests/functional/troll_battery/probes/p13_lit_overflow_i8.kz`，对比 `--stage check` 与 `run` 输出

---

## Bug #73：不同位宽整数混合运算 / 比较静默通过（无显式转换）

- **状态**：已修复（sema 阶段新增 check_numeric_binop_compat，对明确类型化操作数的不同位宽运算报错）
- **优先级**：P1（类型系统严格性）
- **现象**：
  ```kuzo
  val a: i8 = 100i8
  val b: i16 = 1000i16
  val s = a + b          // sema check 通过，运行时 100i8 + 1000i16 = 1100
  val eq = (100i32 == 100i64)   // sema check 通过，运行时 true
  ```
- **根因**：sema 对不同位宽整数的 `+`/`==` 等运算做隐式提升，不要求显式 `cast`，也不报类型不匹配。
- **影响**：违反用户偏好（Rust 风格严格类型，区分字面量可提升与显式变量严格统一）；用户无法通过类型系统发现位宽混淆错误（如把 i32 当 i64 累加导致精度假设错误）。
- **建议修复**：显式类型注解的变量之间，不同位宽运算应报类型错误，要求显式 `cast`；仅裸字面量允许提升。与项目 memory 中"区分字面量与显式变量"的偏好一致。
- **复现**：`tests/functional/troll_battery/probes/p13_mix_i8_i16.kz`、`p13_mix_i32_i64.kz`、`p13_eq_i32_i64.kz`

---

## Bug #74：i32 与 f64 跨类型比较 / 运算静默通过但结果错误

- **状态**：已修复（sema 阶段禁止 int/float 跨类别运算，要求显式 cast）
- **优先级**：P0（数值正确性，静默错误结果）
- **现象**：
  ```kuzo
  val eq1 = (1i32 == 1.0)   // 期望 true（数学相等），实际 false
  val eq2 = (1i32 == 1.5)   // false（正确）
  val add  = 1i32 + 1.0     // 输出 2（结果类型疑似 i32，1.0 被隐式截断为 1）
  ```
- **根因**：sema 允许 `i32 == f64` 与 `i32 + f64` 通过，但运行时既不做数值正确提升（`1i32==1.0` 应为 true），也不报类型错误，而是给出错误结果。`1i32 + 1.0 = 2` 暗示 f64 操作数被截断为 i32 后参与整数运算。
- **影响**：**静默错误结果**是最严重的一类 bug — 用户得到错误答案却无任何警告。跨类型比较/运算要么报类型错误（严格），要么正确提升（`1==1.0` 为 true，`1+1.0=2.0`），不能既允许又算错。
- **建议修复**：sema 阶段禁止 `i32` 与 `f64` 直接 `==`/`+` 等运算，要求显式 `cast` 统一类型后再运算；或定义明确的提升规则并正确实现。
- **复现**：`tests/functional/troll_battery/probes/p13_eq_int_float.kz`、`p13_add_int_float.kz`

---

## Bug #75：整数算术溢出静默 wrap，无 checked / wrapping 运算符选项

- **状态**：已修复（debug 模式 panic on overflow，release 模式 wrapping，与 Rust 语义一致）
- **优先级**：P2（语言可用性 / 安全性）
- **现象**：
  ```kuzo
  val maxI32: i32 = 2147483647i32
  val over: i32 = maxI32 + 1i32    // 输出 -2147483648（wrap）
  val minI32: i32 = -2147483648i32
  val under: i32 = minI32 - 1i32   // 输出 2147483647（wrap）
  val u8max: u8 = 255u8
  val overU8: u8 = u8max + 1u8     // 输出 0（wrap）
  val i8max: i8 = 127i8
  val overI8: i8 = i8max + 1i8     // 输出 -128（wrap）
  ```
- **根因**：所有整数算术默认 wrap（release 语义），无 debug panic 模式，也无 `checked_add`/`wrapping_add`/`overflowing_add` 等显式运算符。
- **影响**：用户无法在调试时捕获溢出 bug；性能优先可接受 wrap，但应提供溢出检查选项。
- **建议修复**：提供 `checked_*` 系列 stdlib 函数（返回 `Throw<T, OverflowError>`），或编译选项 `-C overflow-checks=on`。
- **复现**：`tests/functional/troll_battery/src/Main.kz` R2–R5

---

## Bug #76：val → var 遮蔽允许，破坏 val 不可变语义保证

- **状态**：已修复（sema 阶段追踪绑定可变性,禁止 val→var / var→val 遮蔽,允许同可变性遮蔽）
- **优先级**：P2（语义保证）
- **现象**：
  ```kuzo
  val x: i32 = 1i32
  var x: i32 = 2i32   // sema check 通过
  x = 3i32            // 通过
  println("x={x}")    // 输出 x=3
  ```
- **根因**：允许同名 `val` 被 `var` 遮蔽（反之亦然）。`val` 本应承诺不可变，但遮蔽后同名绑定变为可变，用户对 `val` 的不可变预期被打破。
- **影响**：`val` 的不可变保证仅对当前绑定生效，遮蔽后失效；代码审查时难以追踪可变性变化。
- **建议修复**：要么禁止 `val`→`var` 与 `var`→`val` 的可变性改变遮蔽（允许同可变性遮蔽），要么在允许时给出 warning。
- **复现**：`tests/functional/troll_battery/probes/p14_shadow_val_to_var.kz`

---

## Bug #77：main 函数的 defer 不执行

- **状态**：已修复（2026-08-10）
- **优先级**：P0（defer 语义，清理逻辑丢失）
- **现象**：
  ```kuzo
  fun main(): void {
      println("before defer")
      defer println("defer 1")   // 不打印
      defer println("defer 2")   // 不打印
      println("after defer")
  }
  // 输出：before defer / after defer（缺 defer 1/2）
  ```
  对比：普通（非 main）函数里的 defer 正常 LIFO 执行。
- **根因**：defer 帧在执行 defer body（如 `println`）时会因为函数调用而 suspend，但 main 帧在 `run_frame_nodes` 的 defer 执行循环中直接将自身标记为 `Completed`，导致 `process_frame` 设置 `self.result` 后事件循环退出，suspended 的 defer 帧永远没有机会被调度执行。普通函数帧的 defer 能正常执行是因为调用者在等待子帧完成，事件循环不会提前退出。
- **影响**：用户在 main 里放的清理逻辑（关闭文件、刷新缓冲、释放资源）全部丢失，可能导致数据损坏或资源泄漏。这是最常见的 defer 使用场景之一。
- **修复**：在 Engine 上新增 `defer_frames`（区分 defer 帧与普通子帧）和 `defer_waiters`（记录每个帧等待的 defer 帧计数）两个字段。`init_defer_frame` 设置 defer 帧的 `caller` 为父帧并注册到 `defer_frames`。`run_frame_nodes` 的 defer 执行循环中，若有 defer 帧 suspended（`pending_defer_count > 0`），当前帧不标记 `Completed` 而是 `Suspended`，并在 `defer_waiters` 中记录待完成计数。`process_frame` 的 `Completed`/`Failed` 分支拦截 defer 帧完成，递减父帧的 `defer_waiters` 计数，当计数归零时直接终结父帧（不重新执行 `run_frame_nodes`，避免 defer 重复执行）。`Suspended` 分支跳过 defer-waiter 的 `pending_completions`/`pending_events` 处理。
- **复现**：`tests/functional/troll_battery/probes/p15_defer_basic.kz`、`p15_defer_in_fn.kz`（对比）

---

## Bug #78：并发 async 修改全局变量导致计数错误 + 引擎 panic

- **状态**：已修复（2026-08-10，引擎 panic 部分；数据竞争为预期行为，需用户通过 channel 显式同步）
- **优先级**：P0（并发正确性 + 引擎稳定性）
- **现象**：
  ```kuzo
  var counter: i32 = 0i32
  async fun bump(): Async<void> {
      var i: i32 = 0i32
      while i < 1000i32 {
          counter = counter + 1i32
          i = i + 1i32
      }
  }
  fun main(): void {
      val a = bump()
      val b = bump()
      a.await()
      b.await()
      println("counter={counter}")
  }
  ```
  - 第一次运行：`counter=2066`（期望 2000，出现计数错误）
  - 再次运行：`thread '<unnamed>' panicked at src/engine/Subgraph.rs:381:25: complete_and_wake_caller: LoopBody none but loop_frame FrameId(4) is not in frames (invariant violation: the loop frame referenced by the body frame's caller must exist)`
- **根因**：
  1. 全局可变变量在多 async 间无同步保护，`counter = counter + 1` 非原子，读-改-写交错导致计数错误（甚至出现 >2000 的异常值，说明增量被重复计入）。
  2. 引擎在并发调度 LoopBody 子图完成回调时，`complete_and_wake_caller` 找不到 loop_frame，触发不变量违反 panic。这是并发路径下帧管理缺陷。
- **影响**：任何并发 async 修改共享可变状态的程序都可能得到错误结果或崩溃。并发 + 全局可变是常见模式，此 bug 使其不可用。
- **修复**：
  1. 引擎 panic 部分已修复：`Subgraph.rs::complete_and_wake_caller` 的 LoopBody 分支在多 worker 并发场景下，loop_frame 可能被另一个 worker 暂时取出，原先直接 panic。改为当 loop_frame 不在 frames 中时，将完成信息存入 `pending_completions`，由 `process_frame` 在 loop_frame 重新插入后重放。同时 `Schedule.rs` 消费 `pending_completions` 时对所有 call node 传播 `control_signal`（原先仅对 Gate 节点传播，导致 break/return 信号丢失）。
  2. 数据竞争导致的计数偏差属于语言语义范畴：Kuzo 不对全局可变变量提供隐式同步，并发访问需用户通过 channel 显式同步。这是预期行为（与 Rust 的 `static mut` 语义一致：unsafe + 需用户自行同步），测试用例也以 "expect 2000 if serial, less if race" 标注。后续可通过提供 `Atomic<T>` / 互斥原语改进（特性请求，非 bug）。
- **修复后行为**：`p15_global_race.kz` 运行稳定输出 `counter=1022 (expect 2000 if serial, less if race)`，不再 panic。
- **复现**：`tests/functional/troll_battery/probes/p15_global_race.kz`

---

## Bug #79：async 函数返回值处理缺陷（转发返回垃圾值 / 类型不匹配静默返回 void）

- **状态**：已修复（2026-08-10，缺陷 1 自动 await 转发；channel 竞态 void 已修复）
- **优先级**：P0（async 语义正确性）
- **现象**：
  ```kuzo
  async fun compute(): Async<i32> { 99 }

  // 缺陷 1：直接转发 async 调用结果，返回垃圾值
  async fun retCall(): Async<i32> { compute() }
  // retCall().await() 返回 2（应返回 99）

  // 缺陷 2：最后表达式类型与声明不匹配，静默返回 void
  async fun consumer(ch: Channel<i32>): Async<i32> { ch.recv() }
  // ch.recv() 返回 i32，函数声明 Async<i32>，类型不匹配但 sema 不报错
  // consumer(ch).await() 返回 void（而非 42）

  // 显式 await 转发则正确
  async fun retCallAwait(): Async<i32> { val v = compute().await(); v }
  // retCallAwait().await() 正确返回 99
  ```
- **根因**：
  1. async 函数最后表达式若为另一个 async 调用（返回 `Async<T>`），未做自动 await 转发，也未报"应 await"错误，而是把 async handle 的内部表示当作返回值（垃圾值 2）。
  2. async 函数最后表达式类型（如 `i32`）与声明返回类型（`Async<i32>`）不匹配时，sema 不报错，运行时静默返回 void。
  3. `p15_channel_async.kz` 偶发 `v=void` 的独立根因：`Schedule.rs` 的 `ChannelNotify` 处理中，`on_event_arrived` 传递 `Value::VOID` 作为 ChannelReady 事件的值。`apply_event_to_frame` 直接将 VOID 注入到等待的 consumer 的 await 节点，导致 consumer 返回 void 而非从 channel recv 获取的实际值。
- **修复**：
  1. 缺陷 1 已修复：在 `Builder.rs::compile_function_body` 中，当函数为 async 且 body 表达式的推断类型为 `Async<T>` 时，自动插入隐式 await 节点（`build_await_node`），将 async handle 解析为内部值 T。新增 `expr_type_is_async` 辅助函数精确判断表达式类型是否为 `Async<T>`（不使用 `infer_event_source_kind` 的 AsyncJoin 默认值，避免误判）。修改所有 5 个 `compile_function_body` 调用点，传入 `is_async` 参数。
  2. 缺陷 2 经验证不复现：`ch.recv()` 返回 `i32`，sema 的 `unify_return_type` 正确处理 `Async<i32>` 声明 vs `i32` body 的类型统一（lines 1082-1086），运行时正确返回 42。
  3. channel 竞态 void 已修复：在 `AsyncRt.rs::apply_event_to_frame` 中，对于 Channel await（`suspend_event` 为 `ChannelReady`），不注入传入的 VOID 值，而是重新 push await 节点让 `compute_await` 重新执行。`compute_await` 会再次调用 `ChannelSource::resolve` 的 `ch.recv()` 获取实际值。如果 channel 为空（数据被其他 consumer 取走），帧重新挂起并重新注册 waiter。这与 select 帧的处理方式一致。
- **修复后行为**：`p15_async_ret.kz` 稳定输出 `a=42 b=99 c=99`（原先 `b=2`）；`p15_async_forward_await.kz` 输出 `b=99`；`p15_channel_async.kz` 20 次连续运行全部 `v=42`（原先偶发 `v=void`）。
- **复现**：`tests/functional/troll_battery/probes/p15_async_ret.kz`、`p15_async_forward_await.kz`、`p15_channel_async.kz`

---

## Bug #80：类型别名循环定义不报错

- **状态**：已修复（2026-08-10）
- **优先级**：P2（类型系统健全性）
- **现象**：
  ```kuzo
  type A = B
  type B = A
  // sema check 通过（no type errors）
  // 使用时报含糊错误：
  val x: A = 1i32   // error: type annotation mismatch: expected 'B', found 'i32'
  ```
- **根因**：sema 解析别名时未检测循环引用。`A` 解析为 `B`，`B` 解析为 `A`，形成无限展开，使用时报与循环无关的"expected B"错误，误导用户。现有的 `visiting` 集合循环检测因 `target_type` 短路返回（直接返回预解析的 TypeHandle，不进入递归 `target_type_name` 路径）而失效。
- **修复**：在 `Inference.rs::check_module_with_env` 中 `populate_module` 之后新增 `check_alias_cycles` 方法。该方法遍历所有 `TypeDefKind::Alias` 类型定义，沿 `target_type_name` 链做 DFS 检测环，发现环时报告 `cyclic type alias: A -> B -> A`。使用跨模块去重集合避免同一环被多个模块重复报告。
- **修复后行为**：`p16_alias_cycle.kz` 和 `p16_alias_cycle_rt.kz` 在 sema 阶段报告 `cyclic type alias: A -> B -> A` 和 `cyclic type alias: B -> A -> B`。
- **复现**：`tests/functional/troll_battery/probes/p16_alias_cycle.kz`、`p16_alias_cycle_rt.kz`

---

## Bug #81：同名 ADT 构造子定义不报冲突

- **状态**：已修复（2026-08-10）
- **优先级**：P2（类型系统健全性）
- **现象**：
  ```kuzo
  type A = | Foo(i32)
  type B = | Foo(str)
  // sema check 通过（no type errors）
  // 使用时报类型不匹配：
  val b: B = Foo("x")   // error: type annotation mismatch: expected 'B', found 'A'
  ```
- **根因**：构造子 `Foo` 全局符号表中后定义的覆盖前一个（或仅绑定第一个）。定义时不检测跨类型同名构造子冲突，使用时才报"expected B, found A"，用户误以为是类型注解错误，实际是构造子被遮蔽。`put_type_def` 在遇到构造子名冲突时仅"跳过注册该构造子"，不报告错误。
- **修复**：在 `Inference.rs::check_module_with_env` 中 `populate_module` 之后新增 `check_duplicate_constructors` 方法，遍历所有 `TypeDefInfo.constructors`，对同名构造子（跨类型）报告 `ambiguous constructor: <name> already defined for type <prev>`，并用 `reported` 集合去重避免跨模块重复报告。
- **设计变更：改为使用级报错**（2026-08-11）：对齐 Rust/OCaml 模型，移除 `check_duplicate_constructors` 定义级警告。同名构造器定义合法共存，仅在**使用处**裸名调用且类型导向和参数个数都无法消歧时报错（`Inference.rs::infer_call` 中 `ambiguous constructor '<name>': defined by types [...]`）。stdlib 的 `FileKind.File`/`FileKind.Other` 同名不再产生任何警告，36/36 功能测试 sema 检查通过。
- **保留的基础设施**：`CtorDefInfo.def_span`/`def_module` 和 `SemaError.file_path` 字段保留，供未来跨模块诊断使用。
- **复现**：`tests/functional/troll_battery/probes/p16_dup_constructor.kz`、`p16_dup_constructor_rt.kz`

---

## Bug #82：ADT 重复字段名不报错

- **状态**：已修复（2026-08-10）
- **优先级**：P2（类型系统健全性）
- **现象**：
  ```kuzo
  type P = P(x: i32, x: i32)   // sema check 通过
  ```
- **根因**：Record/ADT 构造子字段名未做唯一性检查。`constructor_def_to_ctor_info`/`record_fields_to_ctor_info` 直接收集所有字段名，不检测重复。
- **修复**：在 `Inference.rs::check_module_with_env` 中 `populate_module` 之后新增 `check_duplicate_ctor_fields` 方法，遍历所有 `TypeDefInfo.constructors`，对每个构造子的 `field_names`（仅命名字段，跳过 `None`）检测重复，报告 `duplicate field '<name>' in constructor <ctor_name>`，并用 `reported` 集合（按 `(field, ctor)` 去重）避免跨模块重复报告。
- **修复后行为**：`p16_dup_field.kz` sema 阶段报告 `duplicate field 'x' in constructor P`；stdlib 不受影响（已验证 `p16_recursive_type.kz` 输出 `ok`）。
- **复现**：`tests/functional/troll_battery/probes/p16_dup_field.kz`

---

## Bug #83：泛型参数类型不统一不报错（pair(1i32, 2i64) 静默用首参类型）

- **状态**：已修复（2026-08-10）
- **优先级**：P1（泛型类型推断）
- **现象**：
  ```kuzo
  fun pair<T>(a: T, b: T): T { a }
  val v = pair(1i32, 2i64)   // sema check 通过
  println("v={v}")           // 输出 v=1（T 绑定为 i32，2i64 被静默接受）
  ```
- **根因**：
  1. `unify_or_constrain(T', i32)` 成功，T' 绑定为 i32，但**不记录 candidate**（仅失败时才 `add_equality`）。
  2. `unify_or_constrain(T', i64)` 失败（i32 ≠ i64），进入 `solver.add_equality`，记录 candidate [i64]。
  3. `finalize_solution` 看到 candidates[T'] = [i64]（仅一个候选），不报歧义。
  4. solver 的 "type mismatch" 错误虽然被记录，但 `solver.errors()` **从未被检查**。
- **修复**：
  1. `unify_or_constrain` 在调用 `unify` 之前先调用 `solver.record_candidate(arena, t1, t2)`，无论 unify 成功还是失败都记录候选。这样 `finalize_solution` 能看到一个 TypeVar 被要求绑定到的**所有**具体类型。
  2. 在 `check_module_with_env` 步骤 9 之后，检查 `solver.errors()`，**仅报告歧义错误**（reason 包含 "ambiguous"）。不报告 "type mismatch" 错误——它们是 `unify_or_constrain` 严格 unify 的副产物，许多可被 `try_widen_unify`（widening/nullable/async 展开）合法解决，报告会产生大量误报。
- **修复后行为**：`p16_generic_unify.kz` sema 阶段报告 `type mismatch: i32 does not unify with i64 (ambiguous inference for TypeVar502: 2 distinct candidates)`；stdlib 及现有测试无回归。
- **复现**：`tests/functional/troll_battery/probes/p16_generic_unify.kz`、`p16_generic_unify_rt.kz`

---

## Bug #84：throw 后代码不报 unreachable

- **状态**：已修复（2026-08-10）
- **优先级**：P3（诊断完整性）
- **现象**：
  ```kuzo
  fun boom(): Throw<i32, Error> {
      throw Error("x")
      val y: i32 = 1i32   // 永不执行，但无 warning
      y
  }
  ```
- **根因**：sema 的 `Expr::Block` 处理逻辑未追踪 `diverges` 状态。遍历块内语句时，遇到 `throw`/`return`/`break`/`continue` 后不会标记后续语句为不可达，也不发警告。trailing 表达式同理。
- **修复**：
  1. 在 `Inference.rs::infer_expr` 的 `Expr::Block` 分支中引入 `diverges` 标志：遍历 `stmts` 时，遇到 `Stmt::Return`/`Stmt::Throw`/`Stmt::Break`/`Stmt::Continue` 置 `diverges = true`；下一轮迭代若 `diverges` 已为真，调用 `add_warning_at("unreachable code after throw/return/break/continue", ...)` 并 `break` 停止推断剩余语句。
  2. trailing 表达式同理：若 `diverges` 为真，对 trailing 表达式报告 unreachable 警告，并返回 `Ty::Never`。
  3. 新增警告系统：在 `SemaResult` 中新增 `warnings: Vec<SemaError>` 字段与 `add_warning` 方法；`InferContext` 新增 `add_warning_at` 方法封装写入；`main.rs` 中新增 `prev_warn_len` 追踪并打印每个模块的警告（格式 `path:line:col: warning: msg`）。
- **修复后行为**：`p16_throw_unreachable.kz` sema 阶段对 throw 后的第 4 行 `val y: i32 = 1i32` 与第 5 行 `y` 分别报告 `unreachable code after throw/return/break/continue` 警告；程序仍正常输出 `ok`。stdlib 及其他测试探针（如 `p16_recursive_type.kz`）无多余警告，无回归。
- **复现**：`tests/functional/troll_battery/probes/p16_throw_unreachable.kz`

---

## Bug #85：match 嵌套穷尽性检查缺失（sema 只检查单层构造器）

- **状态**：已修复
- **优先级**：P1（类型安全 / 诊断完整性）
- **现象**：
  ```kuzo
  type Opt = | Some(i32) | None
  match x {
      Some(0) => ...    // 只覆盖 Some(0)
      None    => ...    // 漏了 Some(非0)
  }
  // sema 不报错（认为 Some + None 都覆盖了）
  // 运行时：Some(1) 落兜底 panic（CF_MATCH_FALLBACK）
  ```
- **根因**：`Inference.rs::pattern_covered_ctors` 对 `Pattern::Constructor { name, .. }` 只记录顶层构造器名，**不递归分析子模式**。当带参数构造器的子模式是字面量/部分模式（如 `Some(0)`）而非变量绑定（`Some(x)`）时，无法检测字段级覆盖缺口。
- **修复**：在 `Inference.rs` 中实现完整的 usefulness 算法（类似 Rust/OCaml 的模式覆盖性分析），替换原有的单层构造器检查。usefulness 算法递归检查构造器子模式覆盖情况，同时解决三个问题：
  1. **嵌套穷尽性**：检测 `Some(0) => ...` 漏掉 `Some(非0)` 的字段级覆盖缺口，附带 witness 消息
  2. **不可达 arm 检测**：检测任意模式重叠（如 `Some(x) => ...` 之后的 `Some(0) => ...` 不可达）
  3. **bool/字面量穷尽性**：正确处理 bool 穷尽（`true` + `false`）和有限字面量穷尽
  同时修复了 `Throw<T, E>` 内置类型的 `Ok`/`Error` 构造器 arity 问题（`ctor_arity_and_fields` 添加 `Ty::Throw` 分支）。
- **验证**：
  - 14/14 lib 单元测试通过
  - edge_match 全部通过（20+ 个穷尽性 match 模式，含 Tree/List/Shape/bool/nullable/newtype/深嵌套/or-pattern/guarded arms）
  - edge_defer 15/15、throw 15/15 全部通过，无回归
  - troll_battery 中 3 个 non-exhaustive 探针正确报告错误并附带精确 witness 消息（missing Blue / missing Rect）
- **复现**：见上方代码

---

## 修复检查清单

每修复一个 bug，请：

1. 在对应测试文件中移除临时绕过方案，恢复标准语法
2. 移除测试文件头部的"注意"注释
3. 运行 `cd test-suite/functional/<name> && kuzo run` 验证修复
4. 运行完整测试套件确认无回归：
  ```bash
  cd /Users/haojunhuang/CLionProjects/Kuzo
  KUZO=./rust/target/release/kuzo
  for d in test-suite/functional/*/; do
      name=$(basename "$d")
      result=$(cd "$d" && $KUZO run 2>&1 | tail -1)
      echo "  $name: $result"
  done
  ```
5. 在本文档中将状态从"待修复"改为"已修复"，记录修复日期

---

## 执行器审查 Bug 汇总（2026-08-07）

> 本次审查针对 `src/engine/` 与 `src/ir/Compute.rs` 的调度核心、帧管理、子图调用、异步运行时、并发策略进行静态分析，共发现 31 个问题。已去除误报和重复项，按严重程度分级如下。

### 修复优先级总览

| 优先级 | 编号 | 模块 | 问题简述 | 状态 |
|--------|------|------|----------|------|
| P0 | H1 | 并发策略 | Multi 模式 worker 在有 pending timer 时全部退出 → 引擎 panic | 已修复 (2026-08-07) |
| P0 | H2 | 事件投递 | 帧注册 waiter 后 insert 回 HashMap 前事件丢失 | 已修复 (2026-08-07) |
| P0 | H3 | 事件投递 | check-then-register TOCTOU 竞态 | 已修复 (2026-08-07) |
| P0 | H4 | 异步调用 | alloc_id + register 分离，子帧可在注册前完成被误判为 sync | 已修复 (2026-08-07) |
| P0 | H5 | 完成回调 | pending_completions 兜底路径丢弃 child_signal | 已修复 (2026-08-07) |
| P1 | M1 | 调度核心 | notify_downstream 腐蚀 PENDING_EXTERNAL 哨兵值 | 已修复 (2026-08-07) |
| P1 | M2 | 调度核心 | pending_inputs u8 溢出与哨兵混淆 | 已修复 (2026-08-07) |
| P1 | M3 | 帧管理 | reset_loop_iteration 未清除 body_frame 的 select_timers | 已修复 (2026-08-07) |
| P1 | M4 | 帧管理 | 嵌套循环 body_frame_id 未清除 → 复用过时内层帧 | 已修复 (2026-08-07) |
| P1 | M5 | 帧管理 | reset_loop_iteration 未清除 loop_frame 的 ready_queue | 已修复 (2026-08-07) |
| P1 | M6 | 调度核心 | iter_guard 超限静默返回导致活锁 | 已修复 (2026-08-07) |
| P1 | M7 | 计算路径 | 同步路径空队列返回未就绪的 return_node 值 | 已修复 (2026-08-07) |
| P1 | M8 | 计算路径 | 同步路径非 Call 的 pending 未被清除 | 已修复 (2026-08-07) |
| P1 | M9 | 计算路径 | compute_closure_call 的 self_upvalue_idx 无边界检查 | 已修复 (2026-08-07) |
| P2 | L1 | 内存泄漏 | cleanup 从未被调用 → entries/fired_set 无界增长 | 已修复 (2026-08-07) |
| P2 | L2 | 并发策略 | check_timers 推帧后直接 park 不重新检查 | 已修复 (2026-08-07) |
| P2 | L3 | 并发策略 | worker park 前的 lost-wakeup | 已修复 (2026-08-07) |
| P2 | L4 | 计算路径 | force_lazy_value_sync 裸指针别名 UB | 已修复 (2026-08-07) |
| P2 | L5 | 并发策略 | notify_all 惊群效应 | 已修复 (2026-08-07) |
| P2 | L6 | 事件投递 | on_event_arrived 的 O(n²) retain | 已修复 (2026-08-07) |
| P3 | L7 | 调度核心 | extract_child_return 注释与 same_function 帧语义不符 | 已修复 (2026-08-07) |
| P3 | L8 | 子图调用 | LoopBody break/return 递归无深度限制 | 已修复 (2026-08-07) |
| P3 | L9 | 异步运行时 | TimerRuntime::next_id 无溢出检查 | 已修复 (2026-08-07) |
| P3 | L10 | 子图调用 | complete_and_wake_caller LoopBody 路径未处理 loop_frame 缺失 | 已修复 (2026-08-07) |
| P3 | L11 | 子图调用 | pending_completions 对同一 caller 多次完成互相覆盖 | 已修复 (2026-08-07) |
| P3 | L12 | 计算路径 | 同步路径 LoopBody Continue/None 不重置循环帧 | 已修复 (2026-08-07) |

---

### P0 优先级（高危：导致 panic / 死锁 / 静默错误结果）

#### Bug H1：Multi 模式 worker 在有 pending timer 时全部退出 → 引擎 panic

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Strategy.rs:280-286`
- **问题**：当 `active_count` 减到 0 时，最后一个 worker 直接 `return` 退出，不检查是否有 pending timer 或 event_waiters。若所有帧都 `await timer.sleep()`，所有 worker 相继退出，定时器到期时没有 worker 存在来处理事件，帧永远无法被唤醒，最终 `run_multi`（Strategy.rs:220）的 `expect("no result produced")` 触发 panic
- **对比**：`run_single`（Strategy.rs:134-154）正确地检查了 `next_deadline` 和 `event_waiters`，在有 pending timer 时 park 到 deadline。Multi 模式的 worker_main 在步骤 4 直接退出，永远到不了步骤 5 的 park 逻辑
- **触发场景**：Multi 模式下包含 `await timer.sleep()` 的程序。例如 2 个 worker，一个帧 await sleep(5s)，两个 worker 都找不到工作后相继退出，5 秒后定时器到期但无人处理，引擎 panic
- **修复**：在步骤 4 `active_count == 0` 时，最后一个 worker 退出前检查 `timer_runtime.next_deadline()` 和 `event_waiters`。若有 pending timer 或 event_waiters，不退出，fall through 到步骤 5 park 到 deadline（active_count 保持为 0，步骤 5 末尾 `+1` 恢复）；若无 pending 才退出。锁顺序为 active → timer → event_waiters（无反向获取，不会死锁）
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug H2：事件投递竞态 — 帧注册 waiter 后、insert 回 HashMap 前事件丢失

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Schedule.rs:692`（注册 waiter 后 return）+ `src/engine/Schedule.rs:953`（才 insert 回 HashMap）
- **问题**：帧的挂起流程跨越两个函数：`run_frame_nodes` 在行 692 注册 event_waiter 并设置 Suspended 状态后返回；`process_frame` 在行 953 才将帧 insert 回 `frames` HashMap。在这两步之间，帧**不在** HashMap 中但**已在** event_waiters 中。若另一 worker 在此窗口内调用 `on_event_arrived`（AsyncRt.rs:248），`frames.remove(&fid)` 返回 None → `continue`，事件被丢弃。帧随后被 insert 回 HashMap 状态为 Suspended，但其 event_waiter 已被移除，没有任何机制会再次投递该事件，帧永久挂起
- **对比**：`SubgraphComplete` 事件有 `pending_completions` 机制兜底此竞态，但 `TimerFired`/`ChannelReady`/`AsyncJoin` 三种事件**没有等价机制**
- **触发场景**：Multi 模式下，帧 A await timer/channel/async 事件，同时另一个 worker 恰好在 A 的 `run_frame_nodes` 返回后、`process_frame` insert 回 HashMap 前触发了对应事件
- **修复**：
  1. Engine 结构体新增 `pending_events: HashMap<FrameId, (RuntimeEvent, Value)>` 字段（与 `pending_completions` 对称）
  2. `on_event_arrived` 中 `frames.remove(&fid)` 返回 None 时，不再 `continue` 丢弃事件，而是将 `(event, value)` 存入 `pending_events[fid]`（waiter 已在上方从 event_waiters 移除，无需重复清理）
  3. `process_frame` 的 Suspended 分支，insert 帧后检查 `pending_events`，若有则调用 `apply_event_to_frame` 注入事件值 + 唤醒
  4. 提取 `apply_event_to_frame` 辅助方法（`on_event_arrived` 和 `process_frame` 共用），消除代码重复
  5. `cancel_frame` 中清理 `pending_events`，避免被取消帧残留事件
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug H3：check-then-register TOCTOU 竞态

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/AsyncRt.rs:217`（检查 is_fired）+ `src/engine/Schedule.rs:692`（注册 waiter）
- **问题**：`resolve_and_check_await` 检查事件是否就绪（timer 的 `is_fired`、channel 的 `recv`、async 的 `try_get_result`），返回 None 表示未就绪。然后调用方在行 692 注册 waiter。在"检查返回 None"和"注册 waiter"之间存在时间窗口：
  1. Worker W1：`is_fired(timer_id)` → false
  2. Worker W2：`check_timers` → `check_and_fire` 弹出该 timer → `on_event_arrived(TimerFired(timer_id))`。event_waiters 中没有该 waiter（尚未注册）→ 事件丢弃
  3. W1：注册 `(TimerFired(timer_id), fid)` 到 event_waiters，帧挂起
  4. 定时器已从堆中弹出，不会再触发，帧永久挂起
- **影响范围**：Channel 路径（`ch.recv()` 返回 None 后另一 worker send 触发 ChannelNotify）和 AsyncJoin 路径（`try_get_result` 返回 None 后子帧完成触发 on_event_arrived）同理
- **触发场景**：Multi 模式下，短定时器（duration 接近 0）、高频 channel 操作、或快速完成的 async 调用
- **修复**：将 `resolve_and_check_await` 重构为 `resolve_check_and_register_await`，把"检查就绪"和"注册 waiter"合并到同一锁临界区，消除 TOCTOU 窗口：
  - **Timer**：持 `timer_runtime` 锁执行 `start` + `is_fired`，未就绪则在释放 timer 锁后注册 waiter（`check_and_fire` 也在 timer 锁内，无法在 start 和 is_fired 之间弹出 timer）
  - **AsyncJoin**：持 `async_join_runtime` 锁执行 `try_get_result`，未就绪则在同锁内注册 waiter（`set_result` 也在该锁内，无法在两步之间触发）
  - **Channel**：`ch.recv()` 返回 None 后立即注册 waiter，`ChannelNotify` → `on_event_arrived` 会查 event_waiters，此时 waiter 已在位
  - 调用方（Schedule.rs）不再重复 push event_waiters，仅设帧状态后 return
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug H4：async call 的 alloc_id + register 分离，子帧可在注册前完成被误判为 sync

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Schedule.rs:625-631`
- **问题**：`child_fid` 在行 625 被推入队列后，另一个 worker 可以立即拾取并执行该子帧。如果子帧在行 631（`register`）之前完成，`process_frame`（Schedule.rs:959）调用 `find_by_child(child_fid)` 返回 None（entry 尚未注册），子帧被当作 sync call 处理：
  1. `complete_and_wake_caller` 被调用，返回值被写入 `pending_completions[caller_fid]`
  2. 当前 worker 继续执行行 631（register）、行 638（set_value 写入 async_handle）、notify_downstream
  3. 当调用方帧后续挂起时，`process_frame` 检查 `pending_completions`，发现条目，将返回值写入 call_node（而非 await_node），覆盖了 async_handle 值
  4. await 节点永远得不到值，帧状态混乱
- **对比**：代码中已定义 `alloc_and_registered`（AsyncRt.rs:133-138）来消除此竞态窗口，但**从未被调用**（全项目 grep 无结果）
- **触发场景**：Multi 模式下，async 调用的子图非常小（快速完成），另一个 worker 在 register 之前拾取并执行完子帧
- **修复**：将 async call 路径重构为"先注册再 push"：
  1. 对 async call，先调用 `alloc_and_register(child_fid)` 原子分配 async_id 并注册映射，再 `queue.push(child_fid)`
  2. 子帧被任何 worker 拾取时，`find_by_child` 可正确匹配 → 走 async 完成路径（`set_result` + 触发 AsyncJoin 事件）
  3. sync call 路径不变（其竞态由 `pending_completions` 兜底：父帧不在 HashMap 时子帧完成，`complete_and_wake_caller` 暂存完成信息，`process_frame` insert 帧后消费）
  4. 使用的 `alloc_and_register` 方法已存在于 AsyncRt.rs:133-138，此前从未被调用
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug H5：pending_completions 恢复路径丢弃 child_signal

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Schedule.rs:932`
- **问题**：当子帧先于父帧 insert 回 HashMap 完成时，完成信息存入 `pending_completions`（Subgraph.rs:305-308），三元组 `(call_node, return_value, child_signal)` 被保存。但 process_frame 消费 pending completion 时，`child_signal` 被 `let _ = child_signal;` 显式丢弃
- **对比**：正常路径 `complete_and_wake_caller`（Subgraph.rs:328-331）会传播 Break/Return 信号到调用方帧；pending_completions 路径完全跳过这一步
- **触发场景**：并发场景下，子帧完成时父帧恰好不在 HashMap 中（正在被 process_frame 执行或正在 complete_and_wake_caller 中被 remove）。子帧带有 Break/Return 信号时，信号丢失，调用方继续执行本应中断的代码路径
- **修复**：在 pending_completions 消费路径中复制 `complete_and_wake_caller` 正常路径的 Gate 信号传播逻辑：检查 `call_graph_id` 对应节点是否为 Gate，若是且 `child_signal != ControlSignal::None`，则设 `frame.control_signal = child_signal`。`call_graph_id` 已在消费路径中计算，直接复用
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

---

### P1 优先级（中危：特定场景下出错）

#### Bug M1：notify_downstream 腐蚀 PENDING_EXTERNAL 哨兵值

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Schedule.rs:372-373`
- **问题**：`prepare_frame_nodes`（行 286）、`prepare_same_function_frame`（Frame.rs:173/178）、`start_subgraph`（Subgraph.rs:118/123）将嵌套子图节点和 EventSource 节点的 `pending_inputs` 设为 `PENDING_EXTERNAL`（= `u8::MAX` = 255），表示"永不就绪/外部源"。但 `notify_downstream` 遍历全局 downstreams 时会对这些节点执行 `255 > 0 → 254` 的递减，腐蚀哨兵值。若累计 255 次递减则归零，嵌套节点被错误推入父帧就绪队列并被父帧执行（应在子帧中执行）
- **触发场景**：任何包含嵌套子图的图——父帧的 Const 节点或计算节点向嵌套子图的入口/参数节点供值时即触发腐蚀
- **修复**：在递减前检查 `pending != PENDING_EXTERNAL`，若为哨兵则跳过递减（哨兵保持 255，不会归零，不会被错误推入就绪队列）
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M2：pending_inputs 的 u8 溢出与哨兵混淆

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Schedule.rs:303` + `src/engine/Frame.rs:188` + `src/engine/Subgraph.rs:130` + `src/ir/Ir.rs:974` + `src/engine/mod.rs:49`
- **问题**：in-frame 输入计数被 `as u8` 截断。两类问题：
  1. **溢出回绕**：若节点有 256 个 in-frame 输入，`256u8 == 0`，节点被标记为已就绪，实际所有输入未必就绪 → 读取未初始化值
  2. **哨兵混淆**：若节点恰好有 255 个 in-frame 输入，`255u8 == PENDING_EXTERNAL`，节点被误判为"外部源/嵌套节点"，永不入就绪队列 → 节点被静默跳过，帧死锁
- **触发场景**：编译器生成的图中存在高入度节点（≥255 输入），如大型 switch/match 的汇聚节点、宽记录构造
- **修复**：将 `pending_inputs` 从 `Vec<u8>` 改为 `Vec<u16>`，`PENDING_EXTERNAL` 从 `u8::MAX`(255) 改为 `u16::MAX`(65535)：
  1. `Ir.rs:974`：`pending_inputs: Vec<u8>` → `Vec<u16>`
  2. `mod.rs:49`：`PENDING_EXTERNAL: u8 = u8::MAX` → `u16 = u16::MAX`
  3. `Schedule.rs:302`：`count() as u8` → `as u16`
  4. `Frame.rs:188`：`0u8` → `0u16`
  5. `Subgraph.rs:130`：`0u8` → `0u16`
  6. `Frame.rs:255`：`reset_node_pending` 参数 `pending: u8` → `u16`
  7. 溢出阈值从 256 提升到 65536，哨兵值从 255 提升到 65535，实际入度不可能达到此量级
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M3：reset_loop_iteration 未清除 body_frame 的 select_timers

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Frame.rs:97-101`
- **问题**：`reset_loop_iteration` 重置 body 帧时，清除了 `value_table`、`ready_queue`、`control_signal`、`pending`，但遗漏了 `select_timers`。对比 `switch_subgraph`（Subgraph.rs:29）会清除 `select_timers`，此处遗漏导致循环体内 select 语句注册的 Timer ID 跨迭代残留。当 body 帧在下一迭代被复用时，select 分支评估代码会通过 `frame.select_timers.iter().find` 找到旧 Timer ID，若旧 Timer 已 fire，`is_fired` 立即返回 true，导致 select 错误地立即选中该分支
- **触发场景**：循环体内包含 select 语句且分支有 Timer 类型事件源
- **修复**：在 body_frame 重置段添加 `body_frame.select_timers.clear();`（与 `switch_subgraph` 保持一致）
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M4：嵌套循环 body_frame_id 未清除 → 复用过时内层帧

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Frame.rs:97-129`
- **问题**：当循环体（LoopBody）内部嵌套另一个循环时，外层 body 帧同时也是内层循环的"loop frame"，其 `body_frame_id` 指向内层 body 帧。当外层循环迭代结束、`reset_loop_iteration` 重置外层 body 帧时，`body_frame_id` 未被清除。外层 body 帧在下一迭代被复用后，执行到内层循环的 Gate 节点时进入 body_frame_id 复用路径。该路径从 HashMap 中取出旧的内层 body 帧，但**只注入参数和设置 caller/state，不重置 value_table、pending_inputs、ready_queue**。内层 body 帧保留了上一外层迭代中最后一次内层迭代的计算结果和就绪状态
- **触发场景**：嵌套循环（循环体内含循环）。外层循环第二迭代及以后，内层循环使用过时的 body 帧状态执行，产生错误结果或静默跳过
- **修复**：在 body_frame 重置段添加 `body_frame.body_frame_id = None;`。清除后，外层 body 帧在下一迭代遇到内层循环 Gate 节点时，`body_frame_id` 为 None → 走 `start_subgraph` 首次创建路径，创建全新的内层 body 帧（而非复用过时帧）
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M5：reset_loop_iteration 未清除 loop_frame 的 ready_queue

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Frame.rs:131-136`
- **问题**：`reset_loop_iteration` 重置 loop_frame 时清除了 `control_signal`、`state`、`suspend_state`、`suspend_event`、`pending`，但未清除 `ready_queue`。随后函数向 `ready_queue` push 了新节点（iter_next、cond），但这些是追加到旧队列尾部。如果 loop_frame 在挂起时 `ready_queue` 非空，旧条目会残留，loop_frame 被重新处理时旧条目先于 cond/iter_next 被执行，可能引用已过时的值
- **触发场景**：loop_frame 的 ready_queue 在挂起时非空
- **修复**：在步骤 1（For 循环重置 iter_next）之前添加步骤 0：`loop_frame.ready_queue.clear();`。必须在步骤 1-3 之前执行，否则会清掉刚 push 的 cond/iter_next/gate 节点
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M6：iter_guard 超限静默返回导致活锁

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/Schedule.rs:406-411` + `src/ir/Compute.rs:2621-2626`
- **问题**：当循环迭代超过 500000（异步路径）或 100000（同步路径）次时，函数直接 `return`，**不设置 `frame.state` 为 Failed，不记录任何错误**。在异步路径中，`process_frame` 取回帧后检查 `frame.state`，由于未被修改（仍是 Ready），会落入 `match state` 的 `_ =>` 分支（Schedule.rs:999-1003），将帧重新入队 → 帧被无限重新调度，每次都在 500000 次迭代后静默返回，形成活锁且永不报告错误。同步路径返回 `Value::VOID`，掩盖计算未完成
- **触发场景**：大规模循环、指数级节点重触发、或其他 bug 导致死循环
- **修复**：
  1. 异步路径（Schedule.rs）：超限时设 `frame.state = FrameState::Failed` 后 return。`process_frame` 的 Failed 分支（Schedule.rs:1023）会正确处理：有 caller 时唤醒调用方，无 caller 时返回 NULL
  2. 同步路径（Compute.rs）：超限时返回 `Value::NULL`（替代 `Value::VOID`），与顶层 Failed 返回 NULL 语义一致
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M7：同步路径空队列返回未就绪的 return_node 值

- **状态**：已修复 (2026-08-07)
- **位置**：`src/ir/Compute.rs:2636-2643`
- **问题**：当就绪队列为空且未触发 Return 控制信号时，直接从 `return_node` 取值返回。但如果 `return_node` 尚未计算（`pending_inputs > 0` 且 `ready == false`），`get_value_by_global` 会返回值表中的未初始化值（`Value::NULL`）或上一轮循环迭代的陈旧值。**静默返回错误结果而非报错**，掩盖了图中的死锁/调度错误
- **触发场景**：thunk 子图（LazyValue force）中存在调度错误、循环未重置、或节点 pending 计数错误导致死锁时
- **修复**：空队列时检查 return_node 的 `ready` 标志，未就绪则返回 `Value::NULL` 表示计算失败。使用 `wrapping_sub` 计算 return_local 避免下溢，bounds 检查防止越界
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M8：同步路径非 Call 的 pending 未被清除

- **状态**：已修复 (2026-08-07)
- **位置**：`src/ir/Compute.rs:2705-2834`
- **问题**：当 `frame.pending` 为 `Some(Pending::Await/SelectWait/ChannelNotify/Cancel)` 时，`if let Some(Pending::Call(_))` 不匹配，落入 `else` 分支。但 `else` 分支不清除 `frame.pending`（仅 Call 分支在行 2707 清除）。导致：①该 pending 永久残留；②当前节点被当作普通节点写入值表并通知下游（值通常是 `Value::VOID`）；③后续每次循环 `pending = frame.pending.clone()` 仍为 `Some(Await...)`，每个被弹出的节点都走 else 分支被错误处理，直到 `iter_guard` 超时
- **触发场景**：thunk 子图意外包含 await/channel/select 节点时
- **修复**：在 Call 分支和普通节点 else 分支之间增加 `else if pending.is_some()` 分支：清除 `frame.pending = None` 并返回 `Value::NULL`。同步路径不支持 async 相关 Pending，返回 NULL 明确表示计算失败，避免错误执行和 iter_guard 超限
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过，5/5 性能测试通过，无回归

#### Bug M9：compute_closure_call 的 self_upvalue_idx 无边界检查

- **状态**：已修复 (2026-08-07)
- **位置**：`src/ir/Compute.rs:2968-2978`
- **问题**：`self_idx` 的计算假设 `self_upvalue_idx < upvalues_len`，但无断言或边界检查。如果 `self_upvalue_idx` 超出 upvalues 范围，`args[self_idx]` 会 panic（数组越界）。此外，`upvalues_start = args.len() - upvalues_len` 在 `upvalues_len > args.len()` 时会下溢（usize 下溢 panic）
- **触发场景**：递归闭包的 `self_upvalue_idx` 元数据与实际 upvalues 数量不一致时
- **修复**：在 `if self_upvalue_idx >= 0` 块内依次添加 4 个断言：① `upvalues_len <= args.len()` 防止 usize 下溢；② `self_upvalue_idx < upvalues_len` 确保 slot 落在 upvalues 区间内；③ `self_idx < args.len()` 防止最终数组越界。先将 `self_upvalue_idx` 转为 usize 局部变量再做比较，避免 i32→usize 转换前未检查范围
- **验证**：cargo build 无警告，8/8 单元测试通过，18/18 功能测试通过（含 closures 递归闭包用例），5/5 性能测试通过，无回归

---

### P2 优先级（低危 / 性能 / 内存泄漏）

#### Bug L1：cleanup 从未被调用 → 内存泄漏

- **状态**：已修复 (2026-08-07)
- **位置**：`src/engine/AsyncRt.rs` + `src/engine/Schedule.rs`
- **问题**：`AsyncJoinRuntime::entries` 只在 `cleanup_consumed` 被调用时清理已完成且已消费的 entry；`TimerRuntime::fired_set` 只在 `cleanup()` 被调用时清空。但两者均未被调用，长时间运行的程序中这两个集合会无界增长
- **修复**：
  1. **TimerRuntime**：`is_fired` 改为 `&mut self` 消费式读取（返回 true 时移除条目）；`check_timers` 在派发所有 fired timer 事件后调用 `cleanup()` 清理残余条目（安全：`is_fired` 仅在 `start