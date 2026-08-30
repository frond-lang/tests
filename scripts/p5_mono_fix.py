# p5_mono_fix.py — Mono.frond 结构清理(嵌套 fun/optional 直访/return-in-match/
# LocalDecl 口径/str? 比较)。
import io

P = r"F:\Projects\Rust\frond-lang\Frond\frondc\src\sema\Mono.frond"
src = io.open(P, encoding="utf-8").read()

def rep(old, new, tag):
    global src
    if old not in src:
        print("MISS:", tag)
        return
    src = src.replace(old, new)
    print("ok:", tag)

# 1) 去嵌套 fun is_tp。
rep("""    fun is_tp(name0: str): bool {
        Semares.list_has_str(type_params, name0)
    }
    val name_to_handle = Map.empty<str, u32>()""",
"""    val name_to_handle = Map.empty<str, u32>()""", "is_tp")
src = src.replace("if is_tp(pname) && !name_to_handle.has(pname) {", "if tp_has(type_params, pname) && !name_to_handle.has(pname) {")
src = src.replace("if is_tp(fp_name) && !name_to_handle.has(fp_name) {", "if tp_has(type_params, fp_name) && !name_to_handle.has(fp_name) {")
src = src.replace("if is_tp(ret_name) && !name_to_handle.has(ret_name) {", "if tp_has(type_params, ret_name) && !name_to_handle.has(ret_name) {")

helper = """
// str[] 包含。
fun tp_has(arr: str[], key: str): bool {
    var i: usize = 0
    while i < arr.len() {
        if arr[i] == key {
            return true
        }
        i = i + 1
    }
    false
}
"""
anchor = "// ─── infer_type_args(泛型调用实参推断)───────────────────────────"
rep(anchor, helper + "\n" + anchor, "tp_has helper")

# 2) Pass 2 lambda:外层捕获 lambda_rt。
rep("""                        match ast.expr(arguments[i]).node {
                            LambdaE(lambda_params, _, lambda_body, _) => {
                                // 函数形参 × lambda 形参注解。""",
"""                        match ast.expr(arguments[i]).node {
                            LambdaE(lambda_params, lambda_rt, lambda_body, _) => {
                                // 函数形参 × lambda 形参注解。""", "lambda destructure")

rep("""                                match fd_ast.ty(fn_ret).node {
                                    TNamed(ret_name) => {
                                        if tp_has(type_params, ret_name) && !name_to_handle.has(ret_name) {
                                            var got: u32? = null
                                            match lambda_body {
                                                LExpr(_) => {
                                                    match ast.expr(arguments[i]).node {
                                                        LambdaE(_, lrt0, _, _) => {
                                                            match lrt0 {
                                                                null => {}
                                                                lrt => {
                                                                    match resolve_tn_flat(a, s, lrt, [], ast) {
                                                                        null => {}
                                                                        h => { got = h }
                                                                    }
                                                                },
                                                            }
                                                        },
                                                        _ => {},
                                                    }
                                                },
                                                LBlock(_) => { got = infer_lambda_return_type(a, s, lambda_params, lambda_body, ast, module_name) },
                                            }
                                            match got {
                                                null => {}
                                                g => { name_to_handle.set(ret_name, g) }
                                            }
                                        }
                                    },
                                    _ => {},
                                }""",
"""                                match fd_ast.ty(fn_ret).node {
                                    TNamed(ret_name) => {
                                        if tp_has(type_params, ret_name) && !name_to_handle.has(ret_name) {
                                            var got: u32? = null
                                            match lambda_rt {
                                                null => {
                                                    got = infer_lambda_return_type(a, s, lambda_body, ast, module_name)
                                                },
                                                lrt => {
                                                    match resolve_tn_flat(a, s, lrt, [], ast) {
                                                        null => {}
                                                        h => { got = h }
                                                    }
                                                },
                                            }
                                            match got {
                                                null => {}
                                                g => { name_to_handle.set(ret_name, g) }
                                            }
                                        }
                                    },
                                    _ => {},
                                }""", "lambda ret")

# 3) infer_lambda_return_type 签名去 lambda_params。
rep("fun infer_lambda_return_type(a: TypeArena, s: SemaRes, lambda_params: Prm[],\n    body: LBody, ast: AstArena, module_name: str): u32? {",
    "fun infer_lambda_return_type(a: TypeArena, s: SemaRes,\n    body: LBody, ast: AstArena, module_name: str): u32? {", "ilrt sig")

# 4) process_call return-in-match 重构。
rep("""    val owner = match ftabs_resolve_owner(tables, func_name, module_name) {
        null => { return }
        m => { m }
    }
    val fd_decl = match ftabs_decl(tables, owner, func_name) {
        null => { return }
        d => { d }
    }""",
"""    val own0 = ftabs_resolve_owner(tables, func_name, module_name)
    if own0 == null {
        return
    }
    val owner = own0 ?? ""
    val fdd0 = ftabs_decl(tables, owner, func_name)
    if fdd0 == null {
        return
    }
    val fd_decl = fdd0 ?? m_decls_dummy()""", "process_call owners")

rep("""    if owner == null {
        owner = ftabs_resolve_owner(tables, method, module_name)
    }
    val owner2 = match owner {
        null => { return }
        m => { m }
    }
    val fd_decl = match ftabs_decl(tables, owner2, method) {
        null => { return }
        d => { d }
    }""",
"""    if owner == null {
        owner = ftabs_resolve_owner(tables, method, module_name)
    }
    if owner == null {
        return
    }
    val owner2 = owner ?? ""
    val fdd0 = ftabs_decl(tables, owner2, method)
    if fdd0 == null {
        return
    }
    val fd_decl = fdd0 ?? m_decls_dummy()""", "process_method owners")

rep("// ─── 调用点处理 ───────────────────────────────────────────────────",
"""// 空 Sd 兜底(类型层面的非空;路径上已被 null 门拦)。
fun m_decls_dummy(): Sd {
    Sd(Span(0, 0), FunDeclD(Priv, "", [], [], null, 0, false, false, [], null))
}

// ─── 调用点处理 ───────────────────────────────────────────────────""", "dummy sd")

# 5) inst 句柄直引。
rep("""    ictx2.inst = Data.new_inst_ctx(func_name, type_args, module_name, in_progress)
    k = 0""",
"""    val instc = Data.new_inst_ctx(func_name, type_args, module_name, in_progress)
    ictx2.inst = instc
    k = 0""", "instc bind")

rep("""    val _bt = Infer.infer_expr(ictx2, a, s, body, ast, fn_env, ictx2.expected_return)
    // Step 1 收尾:局部表并入全局 expr_types(键集 = HM 已覆盖,计数不变)。
    val local_keys = ictx2.inst.local_expr_types.keys()
    var ki: usize = 0
    while ki < local_keys.len() {
        val key = local_keys[ki]
        match ictx2.inst.local_expr_types.get(key) {
            null => {}
            v => { Semares.put_expr(s, key, v ?? 0) }
        }
        ki = ki + 1
    }""",
"""    val _bt = Infer.infer_expr(ictx2, a, s, body, ast, fn_env, ictx2.expected_return)
    // Step 1 收尾:局部表并入全局 expr_types(键集 = HM 已覆盖,计数不变)。
    val local_keys = instc.local_expr_types.keys()
    var ki: usize = 0
    while ki < local_keys.len() {
        val key = local_keys[ki]
        match instc.local_expr_types.get(key) {
            null => {}
            v => { Semares.put_expr(s, key, v ?? 0) }
        }
        ki = ki + 1
    }""", "local merge")

# 6) LocalDeclS walk:引擎口径(无 ExprDeclD)。
rep("""                ExprDeclD(expr, stmt2) => {
                    walk_expr_m(a, expr, ast, tables, in_progress, s, module_name)
                    match stmt2 {
                        null => {}
                        st => { walk_stmt_m(a, st, ast, tables, in_progress, s, module_name) }
                    }
                },
                _ => {},""",
"""                _ => {},""", "localdecl walk")

# 7) Lazy 特判简化。
rep("""                    // Lazy<T> 剥壳;其余丢实参为裸 Generic。
                    if name == "Lazy" && args.len() > 0 {
                        match Populate.from_type_name_full(name) {
                            null => {}
                            _ => {
                                match resolve_tn_flat(a, s, args[0], type_args, ast) {
                                    null => {}
                                    inner => { return inner }
                                }
                            },
                        }
                    }
                    Arena.make_generic(a, name, [])""",
"""                    // Lazy<T> 剥壳;其余丢实参为裸 Generic。
                    if name == "Lazy" && args.len() > 0 {
                        match resolve_tn_flat(a, s, args[0], type_args, ast) {
                            null => {}
                            inner => { return inner }
                        }
                    }
                    Arena.make_generic(a, name, [])""", "lazy flat")

# 8) module_by_path str? 比较。
rep("""            if suffix_ok {
                if hit != null && hit != m {
                    return null
                }
                hit = m
            }""",
"""            if suffix_ok {
                var clash = false
                match hit {
                    null => {}
                    h => {
                        if h != m {
                            clash = true
                        }
                    },
                }
                if clash {
                    return null
                }
                hit = m
            }""", "module_by_path clash")

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("done")
