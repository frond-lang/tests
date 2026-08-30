# p5_wire.py — 片5 Infer.frond 接线:实例化分支/ident 回退/recv 标记/super_targets。
import io

P = r"F:\Projects\Rust\frond-lang\Frond\frondc\src\sema\Infer.frond"
src = io.open(P, encoding="utf-8").read()

def rep(old, new, tag):
    global src
    if old not in src:
        print("MISS:", tag)
        return
    src = src.replace(old, new, 1)
    print("ok:", tag)

# A) infer_call_expr 实例化分支。
rep("""            val resolved_callee = Arena.resolve(a, callee_ty)
            // ModuleRef 调用:模块 env 按尾段名查签名。""",
"""            val resolved_callee = Arena.resolve(a, callee_ty)
            // 实例化模式:HM 已检过,跳 unify;只推实参、返返回类型。
            if ctx.inst != null {
                match Arena.get(a, resolved_callee) {
                    TModuleRef(_) => {
                        val p = Arena.module_ref_parts(a, resolved_callee)
                        val func_name0 = Semares.tail_seg(p.a)
                        match Envs.lookup_local(s.env, p.b, func_name0) {
                            null => {}
                            fn_ty0 => {
                                val inst_fn0 = instantiate_fn_type(a, fn_ty0 ?? 0)
                                match Arena.get(a, inst_fn0) {
                                    TFn(_) => {
                                        val f0 = Arena.fn_parts(a, inst_fn0)
                                        var k0: usize = 0
                                        while k0 < f0.ps.len() && k0 < args.len() {
                                            val _t0 = infer_expr(ctx, a, s, args[k0], ast, env, f0.ps[k0])
                                            k0 = k0 + 1
                                        }
                                        return f0.ret
                                    },
                                    _ => {},
                                }
                            },
                        }
                    },
                    _ => {},
                }
                val inst_callee0 = instantiate_fn_type(a, resolved_callee)
                match Arena.get(a, inst_callee0) {
                    TFn(_) => {
                        val f0 = Arena.fn_parts(a, inst_callee0)
                        var k0: usize = 0
                        while k0 < f0.ps.len() && k0 < args.len() {
                            val _t0 = infer_expr(ctx, a, s, args[k0], ast, env, f0.ps[k0])
                            k0 = k0 + 1
                        }
                        return f0.ret
                    },
                    _ => {},
                }
                add_error_at(s,
                    "cannot call non-function value of type '{Arena.display(a, resolved_callee)}'",
                    e.span.line, e.span.column)
                var z0: usize = 0
                while z0 < args.len() {
                    val _t0 = infer_expr(ctx, a, s, args[z0], ast, env, null)
                    z0 = z0 + 1
                }
                return Arena.make(a, TUnknown)
            }
            // ModuleRef 调用:模块 env 按尾段名查签名。""", "A call-inst")

# B) infer_ident_expr 实例化回退。
rep("""            val sp = ast.expr(expr).span
            add_error_at(s, "undefined variable '{name}'", sp.line, sp.column)
            Arena.fresh_type_var(a)
        },
        _ => { Arena.fresh_type_var(a) }
    }
}""",
"""            // 实例化模式:HM 已解析,查 expr_types 回放;查不到静默新 var。
            if ctx.inst != null {
                val key = Semares.module_expr_key(ctx.current_module_name, expr)
                match Semares.get_expr(s, key) {
                    null => {}
                    info => { return info ?? 0 }
                }
                return Arena.fresh_type_var(a)
            }
            val sp = ast.expr(expr).span
            add_error_at(s, "undefined variable '{name}'", sp.line, sp.column)
            Arena.fresh_type_var(a)
        },
        _ => { Arena.fresh_type_var(a) }
    }
}""", "B ident-fallback")

# C1) Lib 分支 recv 标记。
rep("""                val lib_ty = Arena.make(a, TLib)
                val err_ty = ffi_error_ty(a)
                return Arena.make_throw(a, lib_ty, err_ty)""",
"""                val lib_ty = Arena.make(a, TLib)
                val err_ty = ffi_error_ty(a)
                s.module_func_recv_exprs.set(Semares.module_expr_key(ctx.current_module_name, recv), true)
                return Arena.make_throw(a, lib_ty, err_ty)""", "C1 Lib recv")

# C2) 限定 ctor 方法调用。
rep("""                        match expected {
                            null => {}
                            exp => { unify_or_constrain(ctx, a, f.ret, exp ?? 0) }
                        }
                        return f.ret
                    }
                    // 零参构造器带 () → 报错。""",
"""                        match expected {
                            null => {}
                            exp => { unify_or_constrain(ctx, a, f.ret, exp ?? 0) }
                        }
                        s.module_func_recv_exprs.set(Semares.module_expr_key(ctx.current_module_name, recv), true)
                        return f.ret
                    }
                    // 零参构造器带 () → 报错。""", "C2 qual-ctor recv")

# C3) Path 0a。
rep("""                                val sp = ast.expr(args[k]).span
                                unify_call_arg(ctx, a, s, f.ps[k], arg_ty, sp.line, sp.column, is_null_lit)
                                k = k + 1
                            }
                            return f.ret
                        },
                        _ => {
                            // 零参构造器 `A.TEf()` 形态(Bug#69 族)。""",
"""                                val sp = ast.expr(args[k]).span
                                unify_call_arg(ctx, a, s, f.ps[k], arg_ty, sp.line, sp.column, is_null_lit)
                                k = k + 1
                            }
                            s.module_func_recv_exprs.set(Semares.module_expr_key(ctx.current_module_name, recv), true)
                            return f.ret
                        },
                        _ => {
                            // 零参构造器 `A.TEf()` 形态(Bug#69 族)。""", "C3 path0a recv")

# C4) Path 0b。
rep("""                                                val sp = ast.expr(args[k]).span
                                                unify_call_arg(ctx, a, s, f2.ps[k], arg_ty, sp.line, sp.column, is_null_lit)
                                                k = k + 1
                                            }
                                            return f2.ret""",
"""                                                val sp = ast.expr(args[k]).span
                                                unify_call_arg(ctx, a, s, f2.ps[k], arg_ty, sp.line, sp.column, is_null_lit)
                                                k = k + 1
                                            }
                                            s.module_func_recv_exprs.set(Semares.module_expr_key(ctx.current_module_name, recv), true)
                                            return f2.ret""", "C4 path0b recv")

# D) super_targets。
rep("""                    match expected {
                        null => {}
                        exp => { unify_or_constrain(ctx, a, f.ret, exp ?? 0) }
                    }
                    return f.ret
                },
                _ => { Arena.fresh_type_var(a) }
            }
        },
    }
}""",
"""                    match expected {
                        null => {}
                        exp => { unify_or_constrain(ctx, a, f.ret, exp ?? 0) }
                    }
                    s.super_targets.set("{type_name}" + "\\u{0}" + "{trait_name3}" + "\\u{0}" + "{method}", true)
                    return f.ret
                },
                _ => { Arena.fresh_type_var(a) }
            }
        },
    }
}""", "D super_targets")

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("done")
