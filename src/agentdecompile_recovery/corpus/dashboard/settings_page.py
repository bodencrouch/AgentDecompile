"""Dashboard Settings -> Notifications page: configure the Discord webhook.

Plain form: paste a webhook URL, save it, send a test. The secret is stored
server-side (never echoed back in full). Progress advancements are posted to it
by the recovery pipeline in plain language with an ETA.
"""
from __future__ import annotations


def render_notifications_page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notifications — AgentDecompile</title>
<style>
 body{font:400 14px/1.5 ui-sans-serif,"Segoe UI",system-ui,sans-serif;background:#141517;color:#bbb;margin:0;padding:32px;}
 h1{color:#e6e6e6;font-size:1.2rem;margin:0 0 4px;} .sub{color:#8c8c8c;margin:0 0 24px;}
 .card{max-width:640px;border:1px solid #4b4d50;border-radius:8px;background:#2b2d30;padding:20px;}
 label{display:block;color:#8c8c8c;font-size:12px;text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px;}
 input[type=url]{width:100%;box-sizing:border-box;padding:10px;border:1px solid #4b4d50;border-radius:6px;
   background:#141517;color:#e6e6e6;font-family:ui-monospace,monospace;font-size:12px;}
 .row{display:flex;gap:10px;margin-top:14px;}
 button{padding:9px 16px;border-radius:6px;border:1px solid #4c78cc;background:#4c78cc;color:#fff;cursor:pointer;font:inherit;}
 button.ghost{background:transparent;color:#4c78cc;}
 .status{margin-top:14px;font-size:13px;min-height:20px;}
 .ok{color:#5cba8a;} .err{color:#d36b5c;}
 .hint{margin-top:16px;font-size:12px;color:#6e6e6e;}
</style></head><body>
<h1>Notifications</h1>
<p class="sub">Post decompilation progress to a Discord channel via webhook.</p>
<div class="card">
  <label for="wh">Discord webhook URL</label>
  <input id="wh" type="url" placeholder="https://discord.com/api/webhooks/…" autocomplete="off">
  <div class="row">
    <button onclick="save()">Save webhook</button>
    <button class="ghost" onclick="test()">Send test message</button>
  </div>
  <div class="status" id="st"></div>
  <div class="hint">Advancements post automatically: byte-exact milestones, verified
    byte-identical builds, and an ETA. The URL is stored securely and never shown in full.</div>
</div>
<script>
const st=document.getElementById('st'), wh=document.getElementById('wh');
async function refresh(){
  try{ const d=await (await fetch('/dashboard/api/settings/notifications')).json();
    if(d.configured){ wh.placeholder='configured: '+d.masked; st.innerHTML='<span class="ok">Webhook configured ✓</span>'; } }catch(e){}
}
async function save(){
  const r=await fetch('/dashboard/api/settings/notifications',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({discord_webhook:wh.value.trim()})});
  const d=await r.json();
  st.innerHTML = d.ok ? '<span class="ok">Saved ✓</span>' : '<span class="err">'+(d.error||'failed')+'</span>';
  if(d.ok){ wh.value=''; refresh(); }
}
async function test(){
  st.textContent='Sending…';
  const r=await fetch('/dashboard/api/settings/notifications',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'test',discord_webhook:wh.value.trim()})});
  const d=await r.json();
  st.innerHTML = d.ok ? '<span class="ok">Test message sent — check Discord ✓</span>'
                      : '<span class="err">Test failed: '+JSON.stringify(d.detail||d)+'</span>';
}
refresh();
</script></body></html>"""
