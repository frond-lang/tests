# p5_turbofish.py — CallInfer.rs:撤 pre-unify 消费,改 with_hints 实例化。
import io

P = r"F:\Projects\Rust\frond-lang\Frond\core\src\sema\Inference\CallInfer.rs"
src = io.open(P, encoding="utf-8").read()

def rep(old, new, tag, cnt=1):
    global src
    if old not in src:
        print("MISS:", tag)
        return
    src = src.replace(old, new, cnt)
    print("ok:", tag)

# 1) 撤 Call 臂的 pre-unify 消费块。
rep("""                // HM turbofish consumption (case: silent-void locals): explicit
                // type args on a Call used to be ignored by HM inference —
                // `List.empty<str>()` left T unbound, the 9.4 defaulting pass
                // turned it into void, and match-arm binders over `.get()`
                // results silently degraded to void receivers. Bind each hint
                // to the callee's rigid type params in traversal order
                // (params, then return, first occurrence wins) BEFORE
                // instantiation — instantiate copies the now-bound rigids.
                if !type_args.is_empty() && self.instantiation_ctx.is_none() {
                    let mut rigid_occurrences: Vec<TypeHandle> = Vec::new();
                    self.collect_rigid_occurrences(resolved_callee, &mut rigid_occurrences);
                    for (i, &tn) in type_args.iter().enumerate() {
                        if i >= rigid_occurrences.len() {
                            break;
                        }
                        let hint = self.type_from_ast(tn, ast);
                        let _ = self.arena.unify(hint, rigid_occurrences[i]);
                    }
                }
""", "", "remove pre-unify")

# 2) Call 通用实例化点。
rep("""            // Instantiate the polymorphic function type (replace rigid vars / unbound TypeVars with fresh non-rigid vars)
            // so each call has its own type variables, avoiding type-constraint clashes across calls.
            let inst_callee = self.instantiate_fn_type(resolved_callee);""",
"""            // Instantiate the polymorphic function type (replace rigid vars / unbound TypeVars with fresh non-rigid vars)
            // so each call has its own type variables, avoiding type-constraint clashes across calls.
            // Turbofish: explicit type args bind the first vars positionally
            // (silent-void locals case — see instantiate_fn_type_with_hints).
            let call_hints: &[AstTypeRef] = type_args.as_deref().unwrap_or(&[]);
            let inst_callee = if call_hints.is_empty() {
                self.instantiate_fn_type(resolved_callee)
            } else {
                self.instantiate_fn_type_with_hints(resolved_callee, call_hints, ast)
            };""", "call generic inst")

# 3) consume_turbofish_hints 改为返回实例化结果。
rep("""    /// HM turbofish consumption for method-sugar calls: binds explicit type
    /// args to the underlying generic function's rigid params (see the Call
    /// arm for the rationale — silent-void locals case).
    pub(super) fn consume_turbofish_hints(
        &mut self,
        fn_ty: TypeHandle,
        type_args: &Option<std::vec::Vec<AstTypeRef>>,
        ast: &AstArena<'_>,
    ) {
        let hints: &[AstTypeRef] = type_args.as_deref().unwrap_or(&[]);
        if hints.is_empty() || self.instantiation_ctx.is_some() {
            return;
        }
        let mut rigid_occurrences: Vec<TypeHandle> = Vec::new();
        self.collect_rigid_occurrences(fn_ty, &mut rigid_occurrences);
        for (i, &tn) in hints.iter().enumerate() {
            if i >= rigid_occurrences.len() {
                break;
            }
            let hint = self.type_from_ast(tn, ast);
            let _ = self.arena.unify(hint, rigid_occurrences[i]);
        }
    }
""",
"""    /// HM turbofish consumption for method-sugar calls (instantiation-time
    /// binding; see instantiate_fn_type_with_hints). Returns the instantiated
    /// signature: plain when no hints, hint-bound otherwise.
    pub(super) fn consume_turbofish_hints(
        &mut self,
        fn_ty: TypeHandle,
        type_args: &Option<std::vec::Vec<AstTypeRef>>,
        ast: &AstArena<'_>,
    ) -> TypeHandle {
        let hints: &[AstTypeRef] = type_args.as_deref().unwrap_or(&[]);
        if hints.is_empty() {
            return self.instantiate_fn_type(fn_ty);
        }
        self.instantiate_fn_type_with_hints(fn_ty, hints, ast)
    }
""", "helper rewrite")

# 4) 三处调用点。
rep("""                    if let Some(fn_ty) = found {
                        self.consume_turbofish_hints(fn_ty, type_args, ast);
                        let inst_fn = self.instantiate_fn_type(fn_ty);""",
"""                    if let Some(fn_ty) = found {
                        let inst_fn = self.consume_turbofish_hints(fn_ty, type_args, ast);""", "0a")

rep("""                if let Type::Fn(_) = self.arena.get(recv_resolved_0a) {
                    // Turbofish hints bind the ctor-fn's rigids before any
                    // immutable borrows of arena parts pin the borrow checker.
                    self.consume_turbofish_hints(recv_resolved_0a, type_args, ast);
                    let (_, ret_ty) = self.arena.fn_parts(recv_resolved_0a);""",
"""                if let Type::Fn(_) = self.arena.get(recv_resolved_0a) {
                    let _inst_ctor_fn = self.consume_turbofish_hints(recv_resolved_0a, type_args, ast);
                    let (_, ret_ty) = self.arena.fn_parts(recv_resolved_0a);""", "0b")

rep("""                }) {
                    self.consume_turbofish_hints(fn_ty, type_args, ast);
                    let inst_fn = self.instantiate_fn_type(fn_ty);""",
"""                }) {
                    let inst_fn = self.consume_turbofish_hints(fn_ty, type_args, ast);""", "path0")

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("done")
