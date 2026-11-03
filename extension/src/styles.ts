// Panel and toast styles, isolated in shadow roots so YouTube's CSS can't reach them.
// Chalkboard palette from the website; `.dark` follows YouTube's own dark theme.

export const PANEL_CSS = `
.bl {
  --bg: #f4f7f1; --line: #d9e1d4; --ink: #16291f; --ink-2: #4a5c50; --ink-3: #829183;
  --accent: #1f6b4a; --on-accent: #f4f7f1; --core: #1f6b4a; --example: #2b7ea6; --recap: #c0557a; --skip: #c3ccbf;
  --pending: rgba(244, 247, 241, 0.75);
  font: 14px/1.4 Roboto, "YouTube Sans", Arial, sans-serif; color: var(--ink);
  background: var(--bg); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; display: grid; gap: 10px;
}
.bl.dark {
  --bg: #17241c; --line: #2a3b31; --ink: #eef0e4; --ink-2: #b2bfb0; --ink-3: #7c8b7b;
  --accent: #f2c94c; --on-accent: #17241c; --core: #f2c94c; --example: #8fcbe9; --recap: #f2a0b6; --skip: #3a4c40;
  --pending: rgba(23, 36, 28, 0.72);
}
.bl.collapsed .body { display: none; }
.head { display: flex; align-items: center; gap: 8px; min-width: 0; }
.head b { font-size: 14px; font-weight: 600; }
.logo { width: 18px; height: 18px; border-radius: 5px; background: #1f3529; position: relative; flex-shrink: 0; }
.logo::after { content: ""; position: absolute; left: 6px; top: 4px; border: 5px solid transparent; border-left: 7px solid #f2c94c; border-right: 0; }
.status { color: var(--ink-2); font-size: 13px; display: inline-flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status::before { content: "·"; color: var(--ink-3); }
.status:empty { display: none; }
.live { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.3; } }
button { font: inherit; color: inherit; cursor: pointer; }
.ghost { margin-left: auto; border: 0; background: none; color: var(--ink-3); font-size: 13px; padding: 2px 6px; border-radius: 6px; }
.ghost:hover { color: var(--ink); background: var(--line); }
.body { display: grid; gap: 10px; }
.controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cuts { display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: var(--line); }
.cut { border: 0; background: transparent; border-radius: 8px; padding: 6px 11px; font-size: 13px; font-weight: 500; color: var(--ink-2); display: inline-flex; gap: 6px; }
.cut span { color: var(--ink-3); font-variant-numeric: tabular-nums; }
.cut:hover { color: var(--ink); }
.cut.on { background: var(--accent); color: var(--on-accent); }
.cut.on span { color: inherit; opacity: 0.75; }
.toggle { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer; user-select: none; }
.toggle input { position: absolute; opacity: 0; width: 0; height: 0; }
.toggle span { width: 30px; height: 18px; border-radius: 9px; background: var(--skip); position: relative; transition: background 0.2s; }
.toggle span::after { content: ""; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: transform 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
.toggle input:checked + span { background: var(--accent); }
.toggle input:checked + span::after { transform: translateX(12px); }
.toggle input:focus-visible + span, button:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.tl { position: relative; height: 14px; border-radius: 4px; background: var(--line); overflow: hidden; }
.tl i { position: absolute; top: 2px; bottom: 2px; border-right: 1px solid var(--bg); cursor: pointer; }
.tl i:hover { filter: brightness(1.15); }
.k-core { background: var(--core); }
.k-example { background: var(--example); }
.k-recap { background: var(--recap); }
.k-skip, .tl i.off { background: repeating-linear-gradient(135deg, var(--skip) 0 3px, transparent 3px 6px); }
.pending { position: absolute; top: 0; bottom: 0; right: 0; background: var(--pending); border-left: 1px dashed var(--ink-3); pointer-events: none; }
.head-mark { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: var(--ink); pointer-events: none; }
.foot { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--ink-3); }
.legend { display: inline-flex; align-items: center; gap: 6px; }
.legend em { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-left: 6px; }
.msg { display: grid; gap: 10px; color: var(--ink-2); }
.msg b { color: var(--ink); }
.msg.loading { display: flex; align-items: center; gap: 10px; }
.row { display: flex; gap: 8px; flex-wrap: wrap; }
.btn { border: 1px solid var(--line); background: transparent; border-radius: 8px; padding: 7px 12px; font-size: 13px; font-weight: 500; color: var(--ink); text-decoration: none; }
.btn.primary { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
.spinner { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--line); border-top-color: var(--accent); animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .live, .spinner { animation: none; } }
`;

export const TOAST_CSS = `
.toast {
  display: inline-flex; align-items: center; gap: 10px; padding: 6px 6px 6px 14px; border-radius: 999px;
  font: 500 13px Roboto, Arial, sans-serif; color: #eef0e4; background: rgba(23, 36, 28, 0.92);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4); opacity: 0; transform: translateY(6px); transition: opacity 0.2s, transform 0.2s;
}
.toast.show { opacity: 1; transform: none; pointer-events: auto; }
.toast button { border: 0; border-radius: 999px; padding: 5px 12px; background: #f2c94c; color: #17241c; font: 600 12px Roboto, Arial, sans-serif; cursor: pointer; }
`;
