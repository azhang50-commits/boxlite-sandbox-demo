const $=s=>document.querySelector(s),base=new URL('../api/game/',location.href);let mode='shared',session=null,busy=false,touring=false,generation=0,history=[];
const games={A:{state:null,x:220,y:240,stopped:false,received:0},B:{state:null,x:220,y:240,stopped:false,received:0}};
function escapeHTML(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function message(title,text){$('#observationTitle').textContent=title;$('#observationText').textContent=text;}
function controls(){ $('#startBtn').disabled=busy||touring;$('#faultBtn').disabled=busy||touring||!session||session.mode!==mode||session.state!=='running';$('#tourBtn').disabled=busy||touring;document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=busy||touring);}
function choose(value){mode=value;document.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('selected',b.dataset.mode===mode);b.setAttribute('aria-selected',String(b.dataset.mode===mode));});$('#games').classList.toggle('shared',mode==='shared');$('#modeTitle').textContent=mode==='shared'?'两局游戏，共用一个执行环境。':'两局游戏，各自运行在独立 Box。';$('#modeDescription').textContent=mode==='shared'?'同一个 Box 内，错误的进程清理会波及另一局游戏。':'A 的清理代码只影响自己的 Box，另一台 Box 中的 B 继续运行。';controls();}
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{choose(b.dataset.mode);if(session?.mode!==mode){clearGames('等待启动此模式','点击上方「启动两局游戏」');$('#downloadBtn').disabled=true;message('已切换环境，点击启动。','启动后会在所选环境重新创建两局真实游戏。');}else if(session)useSession(session);});
function overlay(which,title,detail,dead=false){const e=$('#overlay'+which);e.hidden=false;e.classList.toggle('dead',dead);e.querySelector('strong').textContent=title;e.querySelector('span').textContent=detail;}
function stopVisual(which){games[which].stopped=true;$('#status'+which).textContent='进程已停止';$('#status'+which).className='status dead';overlay(which,'游戏已停止',which==='B'?'B 被同一 Box 内的错误清理一起停止':'A 的游戏进程被清理代码停止',true);}
let liveSource=null;
function connectFrames(round,version){
  const source=liveSource=new EventSource(new URL('stream?round='+encodeURIComponent(round),base));
  source.onmessage=event=>{
    if(version!==generation){source.close();return;}
    let packet;try{packet=JSON.parse(event.data);}catch{return;}
    if(packet.round!==round)return;
    for(const which of ['A','B']){
      const state=packet.states[which],g=games[which],expected=session[which.toLowerCase()];
      if(!state||g.stopped||state.round!==round||state.pid!==expected.pid||state.box_id!==expected.box_id)continue;
      if(!g.state||state.tick>g.state.tick){g.received=performance.now();g.samples=(g.samples||0)+1;}
      if(performance.now()-g.received>5000)continue;
      g.state=state;
      $('#score'+which).textContent=state.score;$('#tick'+which).textContent=state.tick;
      $('#pid'+which).textContent=state.pid;$('#status'+which).textContent='正在运行';
      $('#status'+which).className='status live';$('#overlay'+which).hidden=true;
    }
  };
}
setInterval(()=>{
  if(!session)return;
  for(const which of ['A','B']){
    const g=games[which];
    if(!g.stopped&&performance.now()-g.received>5000){
      $('#status'+which).textContent='等待游戏帧';$('#status'+which).className='status';
      overlay(which,'连接暂时中断','未收到新帧；不能据此认定进程已停止。');
    }
  }
},1000);
function clearGames(title,detail){
  generation++;
  if(liveSource){liveSource.close();liveSource=null;}
  for(const k of ['A','B']){
    games[k]={state:null,x:220,y:240,stopped:false,received:performance.now(),samples:0};
    overlay(k,title,detail);$('#status'+k).textContent=title;$('#status'+k).className='status';
    for(const field of ['score','tick','pid'])$('#'+field+k).textContent='—';
    $('#box'+k).textContent='Box ID 将在启动后显示';
  }
}
function useSession(value){
  const previous=session?.id===value.id?structuredClone(games):null;
  session=value;
  clearGames('正在连接游戏进程','读取 Box 内实际计算的画面…');
  $('#downloadBtn').disabled=false;
  for(const k of ['A','B']){
    const spec=value[k.toLowerCase()];
    $('#box'+k).textContent='Box '+spec.box_id;$('#pid'+k).textContent=spec.pid;
    if(value.state==='faulted'&&(k==='A'||value.fault.b_stopped)){
      if(previous?.[k].state){games[k]=previous[k];$('#score'+k).textContent=games[k].state.score;$('#tick'+k).textContent=games[k].state.tick;}
      stopVisual(k);
    }
    else if(['running','faulted'].includes(value.state)){}
    else overlay(k,'运行结果尚未确认','请重新启动演示，读取新一轮真实状态。');
  }
  if(['running','faulted'].includes(value.state)&&!['A','B'].every(k=>games[k].stopped))connectFrames(value.id,generation);
  controls();
}
async function jsonRequest(path,options={}){
  const attempts=options.method==='POST'?1:3;
  const until=performance.now()+12000;
  let last;
  for(let i=0;i<attempts;i++){
    try{
      const response=await fetch(new URL(path,base),{...options,cache:'no-store',signal:AbortSignal.timeout(Math.max(1,until-performance.now()))});
      let result;try{result=await response.json();}catch{result={error:'服务尚未响应，请稍后重试。'};}
      if(!response.ok){const error=Error(result.error||'本次操作未完成');error.status=response.status;throw error;}
      return result;
    }catch(error){
      last=error;
      if((error.status&&error.status<500)||performance.now()>=until)throw error;
      if(i<attempts-1)await new Promise(r=>setTimeout(r,300));
    }
  }
  throw last;
}
async function submitAction(action){
  const request_id=crypto.randomUUID();
  const options={method:'POST',headers:{'Content-Type':'application/json','X-Demo-Request':'1'},
    body:JSON.stringify({mode,request_id,...(action==='fault'?{session_id:session.id}:{})})};
  try{return await jsonRequest(action,options);}
  catch(error){
    if(error.status&&error.status<500)throw error;
    // Inspect the durable job first. A lost POST response may still be accepted.
    try{await jsonRequest('job?id='+encodeURIComponent(request_id));return {job_id:request_id};}
    catch(check){
      if(check.status!==404)throw error;
      // One retry with the SAME id; the server returns an existing job, never repeats it.
      return await jsonRequest(action,options);
    }
  }
}
async function operation(action){busy=true;if(action==='start'){session=null;clearGames('正在启动游戏','等待 Box 内的真实游戏进程就绪…');$('#downloadBtn').disabled=true;}controls();$('#error').hidden=true;$('#progress').hidden=false;const began=performance.now();const clock=setInterval(()=>$('#elapsed').textContent=Math.floor((performance.now()-began)/1000)+'s',200);$('#progressText').textContent=action==='start'?'连接真实 Box，启动游戏进程…':'在 A 的 Box 内执行故障代码…';try{const created=await submitAction(action);const deadline=performance.now()+80000;while(performance.now()<deadline){await new Promise(r=>setTimeout(r,1500));let job;try{job=await jsonRequest('job?id='+encodeURIComponent(created.job_id));}catch(error){if(performance.now()>deadline-12000)throw error;$('#progressText').textContent='连接暂时中断，正在获取真实运行结果…';continue;}if(job.state==='error')throw Error(job.message);if(job.state==='done'){useSession(job.session);history.push({action,session:structuredClone(job.session)});if(action==='fault'){const suffix=mode==='shared'?'Shared':'Isolated';$('#result'+suffix).textContent=mode==='shared'?'A 停止，B 也停止':'A 停止，B 继续运行';$('#result'+suffix).className=mode==='shared'?'verified-bad':'verified-good';$('#proof'+suffix).textContent='真实轮次 '+job.session.id+(mode==='isolated'?' · B 帧数 '+job.session.fault.b_tick_before+' → '+job.session.fault.b_tick_after:' · 已确认两个游戏进程停止');}if(action==='start')message('两局游戏已在 Box 内启动。','观察球的运动与实际帧计数，再点击「让 A 出故障」。');else message(mode==='shared'?'A 出故障，B 也停了。':'A 停止了，B 继续运行。',mode==='shared'?'清理命令在同一个 Box 中找到了两局游戏进程，因此一起停止。':'清理命令只找到了 A 的进程。服务端也验证了 B 的实际帧计数仍在增长。');return job.session;}$('#progressText').textContent=job.message||'等待真实运行结果…';}throw Error('操作超过等待期限。页面已停止等待，可重新启动，不会显示虚构成功结果。');}catch(error){const text=error.name==='TimeoutError'?'连接超时，当前环境可能正在唤醒。请点击启动重试。':error.message;$('#error').textContent=text;$('#error').hidden=false;if(action==='start'){session=null;clearGames('启动未完成','请查看错误提示后重新启动演示。');}else{if(session)session.state='unconfirmed';clearGames('运行结果尚未确认','请重新启动演示，不会将断线当作进程已停止。');}throw error;}finally{busy=false;clearInterval(clock);$('#progress').hidden=true;controls();}}
$('#startBtn').onclick=()=>operation('start').catch(()=>{});$('#faultBtn').onclick=()=>operation('fault').catch(()=>{});
async function watchFrames(){const end=performance.now()+12000;while(performance.now()<end){if(games.A.samples>=2&&games.B.samples>=2&&performance.now()-games.A.received<5000&&performance.now()-games.B.received<5000)return;await new Promise(r=>setTimeout(r,200));}throw Error('游戏画面尚未连接，已暂停自动演示。请手动启动重试。');}
async function watchSurvivor(){const end=performance.now()+12000;while(performance.now()<end){if(games.B.samples>=2&&performance.now()-games.B.received<5000)return;await new Promise(r=>setTimeout(r,200));}throw Error('B 的画面尚未连接，自动演示已暂停。');}
$('#tourBtn').onclick=async()=>{touring=true;document.body.classList.add('tour-on');controls();try{for(const next of ['shared','isolated']){choose(next);await operation('start');await watchFrames();await new Promise(r=>setTimeout(r,2800));await operation('fault');if(next==='isolated')await watchSurvivor();await new Promise(r=>setTimeout(r,2500));}}catch(error){$('#error').textContent=error.message;$('#error').hidden=false;}finally{touring=false;document.body.classList.remove('tour-on');controls();}};
function draw(which){const canvas=$('#canvas'+which),ctx=canvas.getContext('2d'),g=games[which],s=g.state;ctx.setTransform(2,0,0,2,0,0);ctx.fillStyle='#192d25';ctx.fillRect(0,0,440,320);ctx.strokeStyle='#263c2f';ctx.lineWidth=.5;for(let x=0;x<440;x+=22){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,320);ctx.stroke();}for(let y=0;y<320;y+=22){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(440,y);ctx.stroke();}if(!s)return;const colors=which==='A'?['#e7ba78','#bc8d52','#8e6f46']:['#b8d591','#87af6b','#60854c'];for(const brick of s.bricks){ctx.fillStyle=colors[brick.row];ctx.beginPath();ctx.roundRect(brick.x,brick.y,brick.w,brick.h,3);ctx.fill();}if(!g.stopped){g.x+=(s.x-g.x)*.18;g.y+=(s.y-g.y)*.18;}ctx.fillStyle=which==='A'?'#e7bd80':'#c0df9e';ctx.beginPath();ctx.roundRect(s.paddle-35,300,70,7,3);ctx.fill();ctx.shadowColor='#d9e6c1';ctx.shadowBlur=12;ctx.fillStyle='#f4f4da';ctx.beginPath();ctx.arc(g.x,g.y,5,0,Math.PI*2);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#8ca07b';ctx.font='8px monospace';ctx.fillText('BOX '+which+' / SERVER FRAME '+s.tick,14,21);}
function frame(){draw('A');draw('B');requestAnimationFrame(frame);}frame();
$('#downloadBtn').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({exported_at:new Date().toISOString(),session,history},null,2)],{type:'application/json'}));a.download='boxlite-live-game-proof.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
$('#codeBtn').onclick=async()=>{try{const source=await jsonRequest('source');$('#codeContent').innerHTML='<p>故障命令在 A 所在的 Box 内执行，只匹配本演示的游戏程序路径。</p><pre>'+escapeHTML(source.fault)+'</pre><details><summary>查看 Box 内实际游戏程序</summary><pre>'+escapeHTML(source.game)+'</pre></details><p>当前运行记录</p><pre>'+escapeHTML(JSON.stringify(session,null,2))+'</pre>';$('#dialog').showModal();}catch(error){$('#error').textContent=error.message;$('#error').hidden=false;}};$('#closeDialog').onclick=()=>$('#dialog').close();
async function restoreSession(){
  busy=true;controls();
  try{
    const status=await jsonRequest('status');
    $('#runtimeLabel').textContent=status.runtime==='local-boxlite'?'本机 BoxLite · 两台真实 microVM':'两个真实游戏进程 · BoxLite Cloud';
    if(status.active_job){
      choose(status.active_job.mode);
      $('#progress').hidden=false;
      const end=performance.now()+80000;
      while(performance.now()<end){
        const job=await jsonRequest('job?id='+encodeURIComponent(status.active_job.job_id));
        if(job.state==='error')throw Error(job.message);
        if(job.state==='done'){choose(job.session.mode);useSession(job.session);break;}
        $('#progressText').textContent=job.message||'正在恢复运行结果…';
        await new Promise(r=>setTimeout(r,1500));
      }
      if(performance.now()>=end)throw Error('操作结果尚未确认，请重新启动演示。');
    }else if(status.session){choose(status.session.mode);useSession(status.session);}
    if(session)message('已恢复上一轮运行记录。','画面将重新读取真实游戏状态；若环境已自动停止，请重新启动。');
  }catch(error){$('#error').textContent=error.message;$('#error').hidden=false;}
  finally{busy=false;$('#progress').hidden=true;controls();}
}
choose('shared');restoreSession();
