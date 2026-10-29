# -*- coding: utf-8 -*-
# OpenWuwaTappoMod —— 《鸣潮》官方桌宠 Wuwa Tappo 的本地化补丁工具 (精简版)
# Copyright (C) 2026 OpenWuwaTappoMod contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""OpenWuwaTappoMod core: overlay 补丁引擎 + 补丁变换定义 + 注册表定位

overlay 方案: PE 追加 .ovl 节区(任意大小新 brotli 流) + 重指 phf 资源表条目
  {key_ptr, key_len, blob_ptr, blob_len} -- 无等长压缩约束
功能(全部恒注入, 由应用设置页 wtmod_* 键运行时开关):
  drag          任意拖动(多屏并集钳制 + 拖拽触边自动迁移显示器)
  room_drag_top 联机模式下拖动桌宠置顶
  hidenames     隐藏联机好友昵称 / hidecount 隐藏点击数与底栏
  block_fkeys   屏蔽 F1~F12 快捷键
  dblmirror     双击自己或联机成员桌宠垂直镜像
  netdebug      网络调试日志(脱敏)
"""
import brotli
import ctypes
import json
import os
import shutil
import struct
import winreg

# ---------------- 补丁定义(与 case 验证过的变换一致) ----------------

PET_KEY = b"/assets/index-CAndEweT.js"
PANEL_KEY = b"/assets/index-DH_DNc-i.js"
SW_KEY = b"/assets/switchDisplayMonitor-CH1c_9nU.js"
MAIN_KEY = b"/assets/index-DsnG26DH.js"
PATCH_KEYS = (PET_KEY, PANEL_KEY, SW_KEY, MAIN_KEY)

# --- chunk2: 隐藏他人名称 (hidenames) ---
# 用 CSS 隐藏完整容器，保留桌宠外层的右键处理。
HN_RS_ORIG = 'Hs(o.nickname),1)]'
VISIBILITY_IIFE = (
    ';(function(){try{'
    'var style=document.createElement("style");'
    'function sync(){try{'
    'var names=localStorage.getItem("wtmod_hidenames");'
    'names=names===null||names==="1";'
    'var css=(names?".cat-friend__nickname{display:none!important}":"")+'
    '(localStorage.getItem("wtmod_hidecount")==="1"?".pet-dock .pet-info-container{display:none!important}":"");'
    'if(style.textContent!==css)style.textContent=css'
    '}catch(e){}}'
    '(document.head||document.documentElement).appendChild(style);'
    'sync();window.addEventListener("storage",sync);setInterval(sync,500)'
    '}catch(e){}})();'
)
# --- chunk2/4/5: 屏蔽 F1–F12 快捷键 (默认关) ---
# 原生键盘与 DOM 键盘共用 Bc/Nc，其他窗口的 F8 则走独立切屏判定。
BLOCK_FKEY_HELPER = (
    ';(function(){'
    'window.__wtmodBlockFKey=function(key){try{return typeof key==="string"'
    '&&/^F(?:[1-9]|1[0-2])$/i.test(key)'
    '&&localStorage.getItem("wtmod_block_fkeys")==="1"}catch(e){return!1}};'
    'function prevent(e){if(window.__wtmodBlockFKey(e.key))e.preventDefault()}'
    'window.addEventListener("keydown",prevent,!0);'
    'window.addEventListener("keyup",prevent,!0)'
    '})();'
)
BLOCK_FKEY_PET_ANCHORS = (
    ('function Bc(e){',
     'function Bc(e){if(window.__wtmodBlockFKey(e)){Nc(e);return}'),
    ('function Nc(e){',
     'function Nc(e){if(window.__wtmodBlockFKey(e)){'
     'const t=qr.delete(e),o=ma.delete(e);(t||o)&&ql();return}'),
    ('function Fc(e){',
     'function Fc(e){if(window.__wtmodBlockFKey(e.key)){e.preventDefault();return}'),
    ('function Lc(e){',
     'function Lc(e){if(window.__wtmodBlockFKey(e.key)){Nc(e.key);return}'),
    ('const qr=new Set,ma=new Set;',
     'const qr=new Set,ma=new Set;'
     'function _wtmFKeySync(){for(const key of qr)if(window.__wtmodBlockFKey(key))Nc(key)}'
     'window.addEventListener("storage",_wtmFKeySync);'
     'window.addEventListener("wtmod-block-fkeys-change",_wtmFKeySync);'
     'const _wtmFKeyTimer=setInterval(_wtmFKeySync,500);'
     'Ri(()=>{clearInterval(_wtmFKeyTimer);'
     'window.removeEventListener("storage",_wtmFKeySync);'
     'window.removeEventListener("wtmod-block-fkeys-change",_wtmFKeySync)});'),
)
BLOCK_FKEY_SW_ORIG = 'function Dt(t){return Mt.has(t)}'
BLOCK_FKEY_SW_NEW = 'function Dt(t){return !window.__wtmodBlockFKey(t)&&Mt.has(t)}'

# --- chunk2: 双击镜像角色 (dblmirror, 默认关) ---
# Windows 透明窗口通过原生 mouse-button/mouse-move 路由输入，不会生成 DOM dblclick。
# 在原版命中测试后记录按下，释放时识别双击；移动超过阈值即取消，保留原版拖动。
DBL_MIRROR_NATIVE_ANCHORS = (
    ('if(f){const _e=fe.value.find($e=>$e.id===f&&Zt($e)),Ne=',
     'try{window.__wtmodMirror.begin(M.x,M.y,f)}catch(_e){};'
     'if(f){const _e=fe.value.find($e=>$e.id===f&&Zt($e)),Ne='),
    ('const b=Vt(o,l);if(b){if(t==="release"&&e==="left"&&$o)',
    'const b=Vt(o,l);try{if(t==="release"&&e==="left")'
     'window.__wtmodMirror.end(b&&b.x,b&&b.y,Tt.value!==null?'
     'Math.abs(Ln)>.5||Math.abs(Bn)>.5:Lo.value&&Vl.value)}catch(_e){};'
     'if(b){if(t==="release"&&e==="left"&&$o)'),
    ('Cl=await pt("mouse-move",e=>{',
     'Cl=await pt("mouse-move",e=>{try{const _m=Vt(e.payload.x,e.payload.y);'
     'if(_m)window.__wtmodMirror.move(_m.x,_m.y)}catch(_e){};'),
)
DBL_MIRROR_IIFE = (
    ';(function(){try{'
    'var CLS="wtmod-mirror",down=null,last=null,nativeUntil=0;'
    'function on(){try{return localStorage.getItem("wtmod_dblmirror")==="1"}catch(e){return!1}}'
    'function clearAll(){down=null;last=null;try{'
    'for(var els=document.querySelectorAll("."+CLS),i=0;i<els.length;i++)'
    'els[i].classList.remove(CLS)}catch(e){}}'
    'function boxAt(x,y,id){'
    'var hit=document.elementFromPoint(x,y);'
    'if(hit&&hit.closest("button,.local-emotion-bubble,.cat-friend__nickname"))return null;'
    'var n=(id?document.querySelector(\'[data-room-cat-id="\'+Number(id)+\'"]\'):null)||hit;'
    'if(!n)return null;'
    'var box=n.closest(".cat-mainbox,.cat-friend");'
    'return box||(id?n.querySelector(".cat-friend"):null)}'
    'window.__wtmodMirror={'
    'begin:function(x,y,id){'
    'down=null;'
    'if(!on()){last=null;return}'
    'var box=boxAt(x,y,id);'
    'if(!box){last=null;return}'
    'down={box:box,x:x,y:y,time:Date.now(),moved:false}},'
    'move:function(x,y){if(down&&(Math.abs(x-down.x)>5||Math.abs(y-down.y)>5))down.moved=true},'
    'end:function(x,y,moved){'
    'var d=down;down=null;'
    'if(!d)return;var now=Date.now();'
    'if(!on()||!d.box.isConnected||moved||d.moved||!Number.isFinite(x)||!Number.isFinite(y)'
    '||Math.abs(x-d.x)>5||Math.abs(y-d.y)>5||now-d.time>500){last=null;return}'
    'if(last&&last.box===d.box&&now-last.time<=500'
    '&&Math.abs(x-last.x)<=5&&Math.abs(y-last.y)<=5){d.box.classList.toggle(CLS);last=null;nativeUntil=now+800}'
    'else last={box:d.box,x:x,y:y,time:now}}};'
    'document.addEventListener("dblclick",function(e){try{'
    'if(!on()||e.button!==0||Date.now()<nativeUntil)return;'
    'var n=e.target&&e.target.closest?e.target.closest("img.cat"):null;'
    'if(!n)return;var box=n.closest(".cat-mainbox,.cat-friend");'
    'if(box)box.classList.toggle(CLS)'
    '}catch(err){}},!0);'
    'function sync(){try{if(!on())clearAll()}catch(e){}}'
    'var st=document.createElement("style");'
    'st.textContent=".wtmod-mirror{scale:-1 1}.wtmod-mirror .local-emotion-bubble{scale:-1 1}";'
    '(document.head||document.documentElement).appendChild(st);'
    'window.addEventListener("storage",sync);'
    'window.addEventListener("blur",function(){down=null;last=null});'
    'setInterval(sync,500)'
    '}catch(e){}})();'
)

# --- chunk2/4: 拖动相关 (跨显示器) ---
# 1.0.2 重命名: hd→Ed, Jt→Qt, aa→wa, Ne→Oe(watch), Oe→De(nextTick), vi→Ri(dispose),
# Lo→Vo(currentRoomId), Fo→Uo(roomMode), Pt→Tt(拖拽成员id), wo→So(钳制), St→At(缩放)
ROOM_DRAG_Z_OLD = ('function Ed(e,t){const o=Qt(e),l=wa(),f=l?t<l.firstRowColumns?0:'
                   '1+Math.floor((t-l.firstRowColumns)/l.columns):0,b={left:`${o.left}px`,'
                   'top:`${o.top}px`,zIndex:String(l?1e3-f:t+1),visibility:lt.has(e.id)?"visible":"hidden"')
ROOM_DRAG_Z_NEW = ROOM_DRAG_Z_OLD.replace(
    'zIndex:String(l?1e3-f:t+1)',
    'zIndex:String(_wtmRoomZ(e.id,l?1e3-f:t+1))')
ROOM_DRAG_STATE_OLD = 'Oe(lh,()=>{if(Tt.value!==null){Ui=!0;return}Ac(),Fn()})'
ROOM_DRAG_STATE_NEW = (
    'const _wtmRoomTop=W([]),_wtmRoomTopEnabled=W(!1);'
    'function _wtmRoomZ(id,fallback){if(!_wtmRoomTopEnabled.value)return fallback;'
    'const rank=_wtmRoomTop.value.indexOf(id);'
    'return rank<0?fallback:Math.max(1000,dt.value.length)+rank+1}'
    'function _wtmRoomTopSync(){let on=!1;try{on=localStorage.getItem("wtmod_room_drag_top")==="1"}catch(e){}'
    '_wtmRoomTopEnabled.value=on;if(!on&&_wtmRoomTop.value.length)_wtmRoomTop.value=[]}'
    'function _wtmRoomTopStorage(e){if(!e||e.key===null||e.key==="wtmod_room_drag_top")_wtmRoomTopSync()}'
    '_wtmRoomTopSync();'
    'window.addEventListener("storage",_wtmRoomTopStorage);'
    'window.addEventListener("wtmod-room-drag-top-change",_wtmRoomTopSync);'
    'const _wtmRoomTopTimer=setInterval(_wtmRoomTopSync,500);'
    'Ri(()=>{clearInterval(_wtmRoomTopTimer);window.removeEventListener("storage",_wtmRoomTopStorage);'
    'window.removeEventListener("wtmod-room-drag-top-change",_wtmRoomTopSync)});'
    'Oe(Tt,e=>{if(e!==null&&_wtmRoomTopEnabled.value&&Vo.value&&Uo.value!=="idle"'
    '&&dt.value.some(t=>t.id===e))_wtmRoomTop.value=[..._wtmRoomTop.value.filter(t=>t!==e),e]},{flush:"sync"});'
    'Oe([Vo,Uo],()=>{_wtmRoomTop.value=[]},{flush:"sync"});'
    'Oe(()=>fe.value.map(e=>[e.id,e.online?1:0].join(":")).join("|"),()=>{'
    'const ids=new Set(fe.value.filter(e=>e.online).map(e=>e.id));'
    '_wtmRoomTop.value=_wtmRoomTop.value.filter(e=>ids.has(e))},{flush:"sync"});'
    + ROOM_DRAG_STATE_OLD
)
# qe 的 wo 使用桌宠布局及缩放钳制候选位置，拖拽时不传安全区 inset。
# 用同一 wo 求边界，并以相邻鼠标事件的位移判断是否朝外；离开对应边缘后重新武装。
# uv 是官方的循环切屏函数，不按拖动方向选择相邻显示器。
# (1.0.2: qe→Ue, wo→So, St→At, De→Fe, Y→G)
DRAG_LET_OLD = 'let Y=null,ae=0;'
DRAG_LET_NEW = ('let Y=null,ae=0,_wtmEdge=0,_wtmBusy=!1,_wtmX=0,_wtmY=0;'
                'function _wtmDragFail(){try{Promise.resolve('
                'window.__TAURI_INTERNALS__.invoke("write_app_log",'
                '{level:"warn",message:"[WTM] display migration failed or skipped"})'
                ').catch(function(){})}catch(e){}}')
DRAG_BEGIN_OLD = 'G=!1,O=J,K=ve,Fe=C.value,X=D.value,p?.(),y()'
DRAG_BEGIN_NEW = 'G=!1,O=J,K=ve,Fe=C.value,X=D.value,_wtmEdge=0,_wtmX=J,_wtmY=ve,p?.(),y()'
DRAG_MOVE_OLD = 'function Ue(J,ve){if(!N.value||P?.())return;const Je=J-O,We=ve-K;'
DRAG_MOVE_NEW = (DRAG_MOVE_OLD + 'const _dx=J-_wtmX,_dy=ve-_wtmY;_wtmX=J;_wtmY=ve;')
QE_MOVE_OLD = ('const ot=Fe+Je,ft=X+We,Te=So(ot,ft,At(),window.innerWidth,window.innerHeight);'
               'C.value=Te.left,D.value=Te.top,g?.(Te.left-Fe,Te.top-X)')
QE_MOVE_NEW = (QE_MOVE_OLD + ';try{'
               'if(localStorage.getItem("wtmod_drag")==="1"){'
               'const _scale=At(),_lo=So(-Infinity,-Infinity,_scale,window.innerWidth,window.innerHeight),'
               '_hi=So(Infinity,Infinity,_scale,window.innerWidth,window.innerHeight);'
               'let _at=0,_out=0;'
               'if(Te.left<=_lo.left){_at|=1;if(_dx<0)_out|=1}'
               'if(Te.left>=_hi.left){_at|=2;if(_dx>0)_out|=2}'
               'if(Te.top<=_lo.top){_at|=4;if(_dy<0)_out|=4}'
               'if(Te.top>=_hi.top){_at|=8;if(_dy>0)_out|=8}'
               '_wtmEdge&=_at;'
               'if((_out&~_wtmEdge)&&!_wtmBusy){'
               '_wtmEdge|=_out;_wtmBusy=!0;'
               'try{Promise.resolve(uv()).then(function(ok){if(!ok)_wtmDragFail()},'
               'function(){_wtmDragFail()}).finally(function(){_wtmBusy=!1})}'
               'catch(e){_wtmBusy=!1;_wtmDragFail()}}'
               '}else _wtmEdge=0'
               '}catch(e){_wtmDragFail()}')
OT_OLD = ("const t=A(),e=await $();if(!e)return!1;"
          "const n=await t.scaleFactor(),i=await t.outerPosition(),a=await t.innerSize(),"
          "o=e.scaleFactor,c=e.position.x/o,r=e.position.y/o,"
          "u=e.size.width/o,w=e.size.height/o,M=a.width/n,m=a.height/n;"
          "let s=i.x/n,p=i.y/n;"
          "const _=c+Math.max(0,u-M),I=r+Math.max(0,w-m-yt);"
          "s=Math.min(Math.max(s,c),_),p=Math.min(Math.max(p,r),I);"
          "const S=i.x/n,T=i.y/n;"
          "return Math.abs(s-S)<.5&&Math.abs(p-T)<.5?!1:"
          '(await t.setPosition(new K(s,p)),await f("sync_main_window_to_current_monitor"),k(s,p),!0)')
# v2: 并集钳制 + 迁移瞬移抑制。迁移后 ca() 会以"宠物 Dock 逻辑位置(未迁移)"
# 调用本函数, 若据此位移 >160 逻辑像素, 判定为跨屏吸附而非用户意图, 放弃本次钳制
# (窗口留在迁移后的位置, 用户拖放点不丢)。
OT_NEW = ('if(localStorage.getItem("wtmod_drag")!=="1"){' + OT_OLD + '}'
          "const t=A(),e=await j();if(!e||!e.length)return!1;"
          "const n=await t.scaleFactor(),i=await t.outerPosition(),a=await t.innerSize(),"
          "M=a.width/n,m=a.height/n;let c=1/0,r=1/0,_=-1/0,I=-1/0;"
          "for(const E of e){const o=E.scaleFactor,L=E.position.x/o,"
          "O=E.position.y/o,W=E.size.width/o,F=E.size.height/o;"
          "c=Math.min(c,L);r=Math.min(r,O);_=Math.max(_,L+W);I=Math.max(I,O+F)}"
          "_-=M;I-=m+yt;let s=i.x/n,p=i.y/n;const Sx=s,Sy=p;"
          "s=Math.min(Math.max(s,c),_),p=Math.min(Math.max(p,r),I);"
          "if(Math.abs(s-Sx)>160||Math.abs(p-Sy)>160){"
          "console.log('[mod] skip post-switch snap clamp');return!1}"
          "const S=i.x/n,T=i.y/n;"
          "return Math.abs(s-S)<.5&&Math.abs(p-T)<.5?!1:"
          '(await t.setPosition(new K(s,p)),await f("sync_main_window_to_current_monitor"),k(s,p),!0)')

# --- 设置页动态开关 (面板 chunk 末尾追加) ---
# 独立配置字典: 每个开关 = {key, title, sub(说明文字), d(默认态"1"/"0"), feature}
# 克隆原版 setting-item 行, 标题+说明文字形式与原版一致 (行缺 setting-sub 时自动补)。
# 只注入一次: 以首个含 switch 的 setting-item 为锚, 容器级标记防重复。
# 默认语义: 未写入过 localStorage 时, 开关与功能门控均采用 d 字段。
MOD_SWITCHES = (
    {"key": "wtmod_drag", "feature": "drag", "d": "0",
     "title": "(WTM)跨显示器拖动", "sub": "拖到屏幕边缘自动迁移窗口"},
    {"key": "wtmod_room_drag_top", "feature": "room_drag_top", "d": "0",
     "title": "(WTM)联机模式下拖动桌宠时置顶", "sub": "最近拖动的联机成员保持在其他联机桌宠之上"},
    {"key": "wtmod_hidenames", "feature": "hidenames", "d": "1",
     "title": "(WTM)隐藏他人名称", "sub": "联机模式下不显示其他成员的名称框"},
    {"key": "wtmod_hidecount", "feature": "hidecount", "d": "0",
     "title": "(WTM)隐藏点击数和菜单", "sub": "不显示桌宠下方的点击数和菜单栏"},
    {"key": "wtmod_block_fkeys", "feature": "block_fkeys", "d": "0",
     "title": "(WTM)屏蔽F键快捷键", "sub": "屏蔽F1~F12，防止误触切换屏幕等全局快捷键"},
    {"key": "wtmod_dblmirror", "feature": "dblmirror", "d": "0",
     "title": "(WTM)双击镜像角色", "sub": "双击自己或联机成员的桌宠，垂直方向镜像显示"},
)
MOD_SWITCHES_JS = json.dumps(
    [{"k": m["key"], "t": m["title"], "s": m["sub"], "d": m["d"]} for m in MOD_SWITCHES],
    ensure_ascii=True)
MOD_PANEL_INJECT = (
    ';(function(){try{'
    'var MODS=' + MOD_SWITCHES_JS + ';'
    'function wire(row,mod){'
    'const cb=row.querySelector("input[type=checkbox]");if(!cb)return;'
    'var v=null;try{v=localStorage.getItem(mod.k)}catch(e){}'
    'cb.checked=(v===null?mod.d:v)==="1";'
    'cb.addEventListener("change",function(){'
    'try{localStorage.setItem(mod.k,cb.checked?"1":"0");'
    'if(mod.k==="wtmod_room_drag_top")window.dispatchEvent(new Event("wtmod-room-drag-top-change"));'
    'if(mod.k==="wtmod_block_fkeys")window.dispatchEvent(new Event("wtmod-block-fkeys-change"))}catch(e){}})}'
    'function scan(){'
    'if(document.querySelector("[data-wtmod-row]"))return;'
    'var anchor=null;'
    'var rows=document.querySelectorAll(".setting-item");'
    'for(var i=0;i<rows.length;i++){'
    'if(rows[i].querySelector(".setting-content .setting-switch input[type=checkbox]")){anchor=rows[i];break}}'
    'if(!anchor)return;'
    'var last=anchor;'
    'MODS.forEach(function(mod){'
    'var clone=anchor.cloneNode(true);'
    'clone.setAttribute("data-wtmod-row",mod.k);'
    'var tt=clone.querySelector(".setting-title");if(tt)tt.textContent=mod.t;'
    'var sub=clone.querySelector(".setting-sub");'
    'if(!sub){sub=document.createElement("div");sub.className="setting-sub";'
    'var lab=clone.querySelector(".setting-label");if(lab)lab.appendChild(sub)}'
    'if(sub)sub.textContent=mod.s;'
    'wire(clone,mod);last.after(clone);last=clone})}'
    'new MutationObserver(function(){setTimeout(scan,80)}).observe(document.body,{childList:true,subtree:true});'
    'setTimeout(scan,400)}catch(e){}})();'
)
# ---------------- overlay PE 引擎 ----------------

def align(x, a):
    return (x + a - 1) & ~(a - 1)

class PEPatch:
    def __init__(self, data):
        self.data = bytearray(data)
        d = self.data
        self.lfanew = struct.unpack_from('<I', d, 0x3C)[0]
        coff = self.lfanew + 4
        self.nsec, = struct.unpack_from('<H', d, coff + 2)
        opt = coff + 20
        self.opt = opt
        self.sec_align = struct.unpack_from('<I', d, opt + 32)[0]
        self.file_align = struct.unpack_from('<I', d, opt + 36)[0]
        self.sec_table = coff + 20 + struct.unpack_from('<H', d, coff + 16)[0]
        self.image_base = struct.unpack_from('<Q', d, opt + 24)[0]
        self.sections = []
        for i in range(self.nsec):
            h = self.sec_table + i * 40
            vsz, va, rsz, roff = struct.unpack_from('<IIII', d, h + 8)
            self.sections.append((vsz, va, rsz, roff))
        self.rd = next(s for s in self.sections if s[2] > 0x1000000)  # .rdata 特征

    def off2va(self, off):
        vsz, va, rsz, roff = self.rd
        return self.image_base + va + (off - roff)

    def decompress_stream(self, key):
        ko = self.data.find(key)
        assert ko >= 0
        s = ko + len(key)
        d = brotli.Decompressor()
        lo, hi, out = 1, 1, d.process(bytes(self.data[s:s+1]))
        while hi < 40000000:
            r = None
            d2 = brotli.Decompressor()
            try:
                r = d2.process(bytes(self.data[s:s+hi]))
            except Exception:
                break
            out, lo = r, hi
            hi *= 2
        while hi - lo > 1:
            mid = (lo + hi) // 2
            d2 = brotli.Decompressor()
            try:
                r = d2.process(bytes(self.data[s:s+mid]))
                out, lo = r, mid
            except Exception:
                hi = mid
        return out, lo

    def decompress_via_entry(self, key):
        ko = self.data.find(key)
        kva = self.off2va(ko)
        pat = struct.pack('<QQ', kva, len(key))
        i = self.data.find(pat)
        bp, bl = struct.unpack_from('<QQ', self.data, i + 16)
        off = bp - self.image_base
        # .ovl 节区 VA==file offset(构造保证), 通用化: 定位所在节
        for vsz, va, rsz, roff in self.sections:
            if va <= bp - self.image_base < va + max(vsz, rsz):
                off = roff + (bp - self.image_base - va)
                break
        d = brotli.Decompressor()
        return d.process(bytes(self.data[off:off+bl]))

    def repoint(self, key, blob_va, blob_len):
        ko = self.data.find(key)
        kva = self.off2va(ko)
        pat = struct.pack('<QQ', kva, len(key))
        i = self.data.find(pat)
        assert i >= 0, "entry not found: %r" % key
        assert self.data.find(pat, i + 1) < 0
        struct.pack_into('<QQ', self.data, i + 16, blob_va, blob_len)
        return i

    def append_section(self, payload, name=b'.ovl'):
        d = self.data
        assert self.nsec < 16
        last_va = max(va + vsz for vsz, va, rsz, roff in self.sections)
        new_rva = align(last_va, self.sec_align)
        new_off = align(len(d), self.file_align)
        d.extend(b'\x00' * (new_off - len(d)))
        d.extend(payload)
        rsz = align(len(payload), self.file_align)
        d.extend(b'\x00' * (rsz - len(payload)))
        hdr = self.sec_table + self.nsec * 40
        d[hdr:hdr+8] = name.ljust(8, b'\x00')
        struct.pack_into('<IIII', d, hdr + 8, len(payload), new_rva, rsz, new_off)
        struct.pack_into('<I', d, hdr + 36, 0x40000040)
        struct.pack_into('<H', d, self.lfanew + 6, self.nsec + 1)
        soi_off = self.opt + 56
        soi = struct.unpack_from('<I', d, soi_off)[0]
        if new_rva + rsz > soi:
            struct.pack_into('<I', d, soi_off, align(new_rva + rsz, self.sec_align))
        return self.image_base + new_rva, new_off

# ---------------- 注册表定位 / 备份 ----------------

def _strip_q(v):
    return v.strip().strip('"') if isinstance(v, str) else ''

def find_install_dir():
    trees = [(winreg.HKEY_LOCAL_MACHINE, 0),
             (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
             (winreg.HKEY_CURRENT_USER, 0)]
    for root, view in trees:
        try:
            k = winreg.OpenKey(root,
                r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                0, winreg.KEY_READ | view)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                sk = winreg.OpenKey(k, winreg.EnumKey(k, i))
                dn = winreg.QueryValueEx(sk, 'DisplayName')[0].lower()
                if 'wuwatappo' in dn or 'wuwa tappo' in dn:
                    loc = _strip_q(winreg.QueryValueEx(sk, 'InstallLocation')[0])
                    if not loc:
                        loc = os.path.dirname(_strip_q(
                            winreg.QueryValueEx(sk, 'DisplayIcon')[0]))
                    if os.path.isfile(os.path.join(loc, 'WuwaTappo.exe')):
                        return loc
            except OSError:
                continue
    for guess in (r'C:\Program Files\WuwaTappo',
                  r'C:\Program Files (x86)\WuwaTappo'):
        if os.path.isfile(os.path.join(guess, 'WuwaTappo.exe')):
            return guess
    return None

BACKUP_EXT = '.orig'

SUPPORTED_VERSION = "1.0.2"   # 补丁锚点仅针对该主程序版本校准


def is_supported_version(exe_path):
    """仅允许对 1.0.2 主程序打补丁"""
    return _exe_version(exe_path) == SUPPORTED_VERSION


def is_pristine(exe_path):
    """确认实际使用的资源仍为原流，排除已重定向的 overlay 补丁。"""
    try:
        with open(exe_path, 'rb') as f:
            pe = PEPatch(f.read())
        for key in PATCH_KEYS:
            original = pe.decompress_stream(key)[0]
            if pe.decompress_via_entry(key) != original:
                return False
        return HN_RS_ORIG in pe.decompress_via_entry(PET_KEY).decode('utf-8', 'replace')
    except Exception:
        return False

def _exe_version(path):
    """读取 PE 版本资源(ProductVersion, 缺省回退 FileVersion); 不可读返回 None"""
    try:
        v = ctypes.windll.version
        path = str(path)
        size = v.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not v.GetFileVersionInfoW(path, 0, size, buf):
            return None
        p, n = ctypes.c_void_p(), ctypes.c_uint()
        if not v.VerQueryValueW(buf, r"\VarFileInfo\Translation",
                                ctypes.byref(p), ctypes.byref(n)) or n.value < 4:
            return None
        lang, cp = struct.unpack_from('<HH', ctypes.string_at(p, 4))
        q = ctypes.c_void_p()
        for key in ('ProductVersion', 'FileVersion'):
            if v.VerQueryValueW(buf, '\\StringFileInfo\\%04x%04x\\%s'
                                % (lang, cp, key), ctypes.byref(q), ctypes.byref(n)) \
                    and q.value:
                s = ctypes.wstring_at(q)
                if s:
                    return s
        return None
    except Exception:
        return None

def _orig_streams(exe_path):
    """按物理位置提取四个内嵌 JS 的原始 brotli 流(忽略条目重指).

    overlay 补丁只重指 phf 表条目并追加 .ovl 节, 原流仍保留在 key 之后,
    因此打过补丁的 exe 也能据此与备份比对底层官方版本.
    """
    pe = PEPatch(open(exe_path, 'rb').read())
    return [pe.decompress_stream(k)[0] for k in PATCH_KEYS]

def _prepatch_version_check(cur, bak, log):
    """补丁前检查当前 exe 与备份是否同一官方版本.

    比对两层: PE 版本资源字符串 + 内嵌原始资源流(后者可发现版本号未变的换包).
    返回 True 表示一致(或无法判定, 沿用旧逻辑), False 表示不一致.
    """
    cv, bv = _exe_version(cur), _exe_version(bak)
    tag = "当前 %s / 备份 %s" % (cv or '不可读', bv or '不可读')
    if cv and bv and cv != bv:
        log("版本资源不同 (%s)" % tag)
        return False
    try:
        if _orig_streams(cur) == _orig_streams(bak):
            log("版本一致性校验通过 (%s)" % tag)
            return True
        log("内嵌资源流与备份不一致 (%s)" % tag)
        return False
    except Exception:
        if cv and bv:
            log("版本一致性校验通过 (%s; 资源流比对跳过)" % tag)
            return True
        log("无法判定版本一致性 (%s), 按同一版本处理" % tag)
        return True

# ---------------- 补丁构建 ----------------

def build_assets(exe_path, log):
    """构建补丁流。全部功能恒注入, 由应用设置页 (wtmod_* 键) 运行时开关。"""
    pe = PEPatch(open(exe_path, 'rb').read())
    assets = []

    js2, _ = pe.decompress_stream(PET_KEY)
    js2 = js2.decode('utf-8')
    for old, new in BLOCK_FKEY_PET_ANCHORS:
        assert js2.count(old) == 1, "F键屏蔽锚点异常: %r" % old[:60]
        js2 = js2.replace(old, new, 1)
    # 恒注入，运行时开关保留；所有拖拽锚点必须唯一匹配 1.0.2。
    for old, new in ((DRAG_LET_OLD, DRAG_LET_NEW),
                     (DRAG_BEGIN_OLD, DRAG_BEGIN_NEW),
                     (DRAG_MOVE_OLD, DRAG_MOVE_NEW),
                     (QE_MOVE_OLD, QE_MOVE_NEW)):
        assert js2.count(old) == 1, "拖拽移动锚点异常: %r" % old[:60]
        js2 = js2.replace(old, new, 1)
    # 最近有效拖动成员保持置顶；房间、在线状态和开关变化时清理。
    assert js2.count(ROOM_DRAG_Z_OLD) == 1, "联机拖动层级锚点异常"
    js2 = js2.replace(ROOM_DRAG_Z_OLD, ROOM_DRAG_Z_NEW, 1)
    assert js2.count(ROOM_DRAG_STATE_OLD) == 1, "联机拖动状态锚点异常"
    js2 = js2.replace(ROOM_DRAG_STATE_OLD, ROOM_DRAG_STATE_NEW, 1)
    js2 = js2.rstrip('\n') + '\n'
    # 校验原版渲染锚点，样式隐藏完整容器，不触及右键入口。
    assert js2.count(HN_RS_ORIG) == 1, "昵称渲染锚点缺失"
    assert js2.count('by={class:"cat-friend__nickname web-bold-font"}') == 1, "昵称容器锚点缺失"
    assert js2.count('Dy={class:"pet-info-container"}') == 1, "底栏容器锚点缺失"
    # 恒注入: 原生鼠标输入不会派发 DOM 双击事件。
    for old, new in DBL_MIRROR_NATIVE_ANCHORS:
        assert js2.count(old) == 1, "双击镜像输入锚点异常: %r" % old[:60]
        js2 = js2.replace(old, new, 1)
    js2 = js2.rstrip('\n') + VISIBILITY_IIFE + DBL_MIRROR_IIFE + '\n'
    assets.append((PET_KEY, brotli.compress(js2.encode(), quality=11)))
    log("[1/4] 主窗口 chunk (拖动/置顶/隐藏/F键/双击镜像 恒注入+设置页开关) OK")

    js3, _ = pe.decompress_stream(PANEL_KEY)
    js3 = js3.decode('utf-8')
    js3 = js3.rstrip('\n') + MOD_PANEL_INJECT + '\n'
    assets.append((PANEL_KEY, brotli.compress(js3.encode(), quality=11)))
    log("[2/4] 面板 chunk (设置页动态开关×%d) OK" % len(MOD_SWITCHES))

    js4, _ = pe.decompress_stream(SW_KEY)
    js4 = js4.decode('utf-8')
    assert js4.count(OT_OLD) == 1
    js4 = js4.replace(OT_OLD, OT_NEW)
    assert js4.count(BLOCK_FKEY_SW_ORIG) == 1, "F8快捷键屏蔽锚点异常"
    js4 = js4.replace(BLOCK_FKEY_SW_ORIG, BLOCK_FKEY_SW_NEW, 1)
    assets.append((SW_KEY, brotli.compress(js4.encode(), quality=11)))
    log("[3/4] 多屏拖动限制 OK")

    # 恒注入: F键屏蔽助手 (全局 __wtmodBlockFKey, 供 SW/PET 钩子调用)
    js5, _ = pe.decompress_stream(MAIN_KEY)
    js5 = js5.decode('utf-8')
    main_anchor = 'function setLocalStorage(e,t){window.localStorage.setItem(e,t)}class Request{'
    assert js5.count(main_anchor) == 1, "F键助手锚点异常"
    js5 = js5.replace(main_anchor, BLOCK_FKEY_HELPER + main_anchor, 1)
    assets.append((MAIN_KEY, brotli.compress(js5.encode(), quality=11)))
    log("[4/4] F键助手 OK")
    return pe, assets

def run_patch(exe_path, out_path, log):
    ver = _exe_version(exe_path)
    if ver != SUPPORTED_VERSION:
        raise RuntimeError(
            "主程序版本为 %s，本工具仅支持 %s。"
            "请先卸载/恢复官方 1.0.2 版本后再打补丁。"
            % (ver or "未知", SUPPORTED_VERSION))
    log("主程序版本校验通过: %s" % ver)
    in_place = os.path.abspath(exe_path) == os.path.abspath(out_path)
    bak = exe_path + BACKUP_EXT
    bak_msg = None          # 补丁构建成功后写入的备份: 'new'=新建 / 'rebuild'=以当前版本重建
    if in_place:
        if os.path.exists(bak):
            if _prepatch_version_check(exe_path, bak, log):
                log("检测到已有备份 —— 以备份为源基准重新打补丁")
                exe_path = bak
                if not is_pristine(exe_path):
                    raise RuntimeError("备份文件不是原版(或已损坏), 请先恢复或重新安装")
            else:
                # 版本不一致(官方程序已更新): 以当前 exe 为基准打补丁,
                # 备份在 build_assets 成功后重建(锚点不符时旧备份得以保留)
                log("!! 当前程序与备份版本不一致 —— 直接使用当前 exe 打补丁并重建备份")
                bak_msg = 'rebuild'
                if not is_pristine(exe_path):
                    log("   注意: 当前 exe 未通过原版锚点校验, 若为官方新版可能需更新补丁定义")
        else:
            log("未发现备份 —— 将以当前 exe 为基准打补丁")
            if not is_pristine(exe_path):
                raise RuntimeError("当前 exe 不是原版(或已损坏), 且没有备份, 请先恢复或重新安装")
            bak_msg = 'new'
    pe, assets = build_assets(exe_path, log)
    if bak_msg:
        shutil.copy2(exe_path, bak)
        log(("已备份原版 -> %s" if bak_msg == 'new'
             else "已以当前版本重建备份 -> %s") % bak)
    body = b''.join(stream for _, stream in assets)
    base_va, _ = pe.append_section(body)
    off = 0
    for key, stream in assets:
        pe.repoint(key, base_va + off, len(stream))
        log("   重定向指针 %-42s len=%d" % (key.decode()[:42], len(stream)))
        off += len(stream)
    tmp = out_path + '.tmp'
    open(tmp, 'wb').write(bytes(pe.data))
    try:
        os.replace(tmp, out_path)
    except PermissionError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("写入被拒绝: 请以管理员身份运行本工具, 并确保 WuwaTappo 已完全退出")
    log("完成 -> %s (%d 字节)" % (out_path, len(pe.data)))
    # 自验
    chk = PEPatch(open(out_path, 'rb').read())
    for key, stream in assets:
        got = chk.decompress_via_entry(key)
        assert got == brotli.decompress(stream), key
    log("补丁检测通过: %d 个条目指针一致" % len(assets))
    log("补丁完成！")

