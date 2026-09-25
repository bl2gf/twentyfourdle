'use strict';
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = value => String(value || '').replaceAll('*','×').replaceAll('/','÷').replaceAll('-','−');
let state = null, selectedClub = '', ranking = 'speed', clockOffset = 0, busy = false, editing = false;
let inviteCode = new URLSearchParams(location.search).get('join') || '';
let toastTimer;
const modal = $('#modal');

function timeLabel(ms, tenths = true) {
  const n = Math.max(0, ms || 0), minutes = Math.floor(n / 60000);
  return `${String(minutes).padStart(2,'0')}:${String(Math.floor(n/1000)%60).padStart(2,'0')}${tenths?'.'+Math.floor(n%1000/100):''}`;
}
function solved() { return state?.attempt?.elapsed != null; }
function toast(message) { $('#toast').textContent = message; $('#toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.add('hidden'), 4000); }
async function api(path, body) {
  const response = await fetch('/api/' + path, body === undefined ? {cache:'no-store'} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  let value;
  try { value = await response.json(); } catch { throw Error('Could not reach the game. Please try again.'); }
  if (!response.ok) throw Error(value.error || 'Please try again.');
  return value;
}
function accept(value) {
  if (state?.day && state.day !== value.day) { $('#expression').value = ''; editing = false; toast('A new daily puzzle is ready!'); }
  state = value;
  clockOffset = state.serverNow - Date.now();
  render();
}
function render() {
  $('#day-label').textContent = new Date(state.day+'T12:00:00Z').toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'});
  $('#profile-button').textContent = state.player ? state.player.name.charAt(0).toUpperCase() : '?';
  $('#profile-button').title = state.player?.name || 'Choose a player name';
  $('#start-button').disabled = false;
  $('#start-button').innerHTML = `${state.player?'Reveal & start':'Play today’s puzzle'} <span>↗</span>`;
  const started = Boolean(state.attempt), done = solved();
  $('#start-area').classList.toggle('hidden',started);
  $('#solution-form').classList.toggle('hidden',!started || (done && !editing));
  $('#timer-label').textContent = done ? 'FIRST SOLVE' : 'YOUR TIME';
  $('#submit-button').innerHTML = `${done?'Check simpler solution':'Check my solution'} <span>↵</span>`;
  $('#cards').innerHTML = state.cards ? state.cards.map((n,i) => `<button type="button" class="number-card" data-card="${n}" aria-label="Insert number ${n}, tile ${i+1}">${n}</button>`).join('') : Array(4).fill('<div class="number-card hidden-card">?</div>').join('');
  $('#cards').querySelectorAll('[data-card]').forEach(button => button.addEventListener('click',() => {if(done && !editing) return; insert(button.dataset.card);}));
  $('#result').classList.toggle('hidden',!done);
  if(done) {
    const a = state.attempt, optimal = state.optimal, best = a.best_score === optimal.score;
    $('#result').innerHTML = `<div class="success-box"><span class="eyebrow">DAILY CHALLENGE COMPLETE</span><h3>That’s twenty-four. Nicely done.</h3><div class="score-line"><div><strong>${timeLabel(a.elapsed)}</strong><span>Your first solve</span></div><div><strong>${a.best_score} pts</strong><span>${best?'Best possible simplicity!':'Your simplicity score'}</span></div></div><p class="equation">${escapeHTML(pretty(a.best_expression))} = 24</p><div class="result-actions"><button class="secondary" id="share-result">Share result ↗</button>${!best?'<button class="plain" id="improve">Try a simpler solution</button>':''}</div><details><summary>Compare with the simplest solution</summary><p class="equation">${escapeHTML(pretty(optimal.expression))} = 24</p><p>Best possible: <strong>${optimal.score} points.</strong> Lower is simpler; ties are equally good.</p></details></div>`;
    $('#share-result').addEventListener('click', shareResult);
    $('#improve')?.addEventListener('click',() => {editing=true;$('#solution-form').classList.remove('hidden');$('#expression').value='';$('#expression').focus();});
  }
  renderBoard();
  updateClocks();
}
function renderBoard() {
  const clubs = state.clubs || [];
  if(!clubs.some(c => c.id === selectedClub)) selectedClub = clubs[0]?.id || '';
  $('#club-picker').classList.toggle('hidden', !clubs.length);
  $('#club-select').innerHTML = clubs.map(c => `<option value="${escapeHTML(c.id)}"${c.id===selectedClub?' selected':''}>${escapeHTML(c.name)}</option>`).join('');
  const club = clubs.find(c => c.id === selectedClub);
  $('#spoiler-note').textContent = solved() ? 'First-solve time is locked. Simpler solutions can still improve.' : 'Solutions unlock after you solve today’s puzzle.';
  if(!club) {
    $('#leaderboard').innerHTML = '<div class="empty-board"><span class="empty-symbol">01 —</span><h3>Your circle starts with you.</h3><p>Create a group, invite your friends,<br>and see who gets to 24 first.</p></div>';
    return;
  }
  const rows = [...club.players].sort((a,b) => {
    if(a.elapsed==null && b.elapsed==null) return a.name.localeCompare(b.name);
    if(a.elapsed==null) return 1;
    if(b.elapsed==null) return -1;
    return ranking==='speed' ? a.elapsed-b.elapsed : a.best_score-b.best_score || a.elapsed-b.elapsed;
  });
  let lastMetric = null, place = 0;
  $('#leaderboard').innerHTML = '<div class="leader-list">' + rows.map((p,i) => {
    const done = p.elapsed != null, metric = ranking==='speed'?p.elapsed:p.best_score;
    if(metric !== lastMetric) place = i+1;
    lastMetric = metric;
    const equation = ranking==='speed'?p.first_expression:p.best_expression;
    return `<div class="leader-row"><span class="place">${done?String(place).padStart(2,'0'):'—'}</span><div><div class="name">${escapeHTML(p.name)}${p.id===state.player.id?'<span class="you">YOU</span>':''}</div>${equation?`<div class="equation">${escapeHTML(pretty(equation))} = 24</div>`:''}</div><div class="metric">${done?(ranking==='speed'?timeLabel(p.elapsed):p.best_score+' pts'):'—'}<span class="label">${done?(ranking==='speed'?'first solve':'lower is simpler'):'not solved'}</span></div></div>`;
  }).join('')+'</div>';
}
function updateClocks() {
  if(!state) return;
  $('#timer').textContent = timeLabel(solved()?state.attempt.elapsed:state.attempt?Date.now()+clockOffset-state.attempt.started:0);
  const remaining = Math.max(0,new Date(state.resetsAt).getTime()-Date.now()-clockOffset);
  const s = Math.floor(remaining/1000);
  $('#reset-countdown').textContent = `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s/60)%60).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
  document.title = state.attempt && !solved() ? `${timeLabel(Date.now()+clockOffset-state.attempt.started,false)} · Twentyfourdle` : 'Twentyfourdle — Your daily dose of 24';
}
function insert(token) {
  const input = $('#expression');
  const start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? input.value.length;
  const next = input.value.slice(0,start)+token+input.value.slice(end);
  if(next.length>120) return;
  input.value=next;input.focus();input.setSelectionRange(start+token.length,start+token.length);
  $('#game-message').textContent='';
}
function showModal(html) { $('#modal-content').innerHTML=html; if(!modal.open) modal.showModal(); }
function showHelp() {
  showModal(`<span class="eyebrow">A LITTLE MATH. A LOT OF POSSIBILITIES.</span><h2>Four numbers. Make 24.</h2><p>Use each number exactly once. Combine them with addition, subtraction, multiplication, division, and parentheses.</p><div class="score-tip"><strong>For example: 1, 2, 3, 4</strong><p class="equation">(1 + 2 + 3) × 4 = 24</p></div><ul><li>Your timer starts when you reveal the numbers. It keeps running if you leave or refresh.</li><li>Your first correct solution locks in your time.</li><li>After solving, compare your friends’ solutions and try to improve your simplicity score.</li><li>Every puzzle is solvable. Everyone gets the same numbers, changing at midnight UTC.</li></ul><p>This is friendly competition: use your own brain, and keep the answers a secret until your friends finish.</p>`);
}
function showScoring() {
  showModal(`<span class="eyebrow">THE ART OF KEEPING IT SIMPLE</span><h2>Less mental math wins.</h2><p>All valid answers use three operations, so counting operations would always tie. Our <strong>simplicity score</strong> gives each operation a cost:</p><table class="score-table"><thead><tr><th>Operation</th><th>Points</th></tr></thead><tbody><tr><td>Add or subtract</td><td>1</td></tr><tr><td>Multiply</td><td>2</td></tr><tr><td>Divide</td><td>3</td></tr></tbody></table><p>Add the costs. Lower is simpler. Parentheses are free. Fractions and negative intermediate values are allowed.</p><div class="score-tip">(1 + 2 + 3) × 4 → 1 + 1 + 2 = <strong>4 points</strong></div><p>This is a game rule, not an objective measure of mathematical elegance. After you solve, we show a lowest-scoring solution found by checking all allowed combinations. Equal scores tie.</p>`);
}
function profileFlow(after) {
  showModal(`<span class="eyebrow">${state?.player?'YOUR PLAYER':'WELCOME TO THE CIRCLE'}</span><h2>${state?.player?'Make yourself at home.':'What should we call you?'}</h2><p>${state?.player?'Your scores are saved with this player.':'Pick a name your friends will recognize. No email required.'}</p><form id="profile-form"><label for="player-name">Player name</label><input id="player-name" maxlength="24" required autocomplete="nickname" value="${escapeHTML(state?.player?.name||'')}" placeholder="Your name"><p class="modal-error" role="alert"></p><button class="primary" type="submit">${state?.player?'Save name':'Let’s play'} <span>↗</span></button></form>${!state?.player?'<button class="plain" id="recover-button">Already played? Restore your player</button>':'<p>Keep your original recovery key to restore your scores on another browser. Restoring signs out the previous browser.</p>'}`);
  $('#profile-form').addEventListener('submit',async event => {
    event.preventDefault(); const button = event.target.querySelector('button');button.disabled=true;
    try {
      const result = await api('profile',{name:$('#player-name').value});accept(result);
      if(result.recoveryKey) {
        showModal(`<h2>You’re in, ${escapeHTML(state.player.name)}.</h2><p>Save this private recovery key to get your scores back if you switch browsers or clear cookies. Anyone with the key can use your player.</p><code class="recovery-key">${escapeHTML(result.recoveryKey)}</code><button class="secondary" id="copy-key">Copy recovery key ↗</button><button class="primary" id="continue-player">Continue <span>↗</span></button>`);
        $('#copy-key').onclick=()=>copyText(result.recoveryKey,'Recovery key copied. Keep it somewhere safe.');
        $('#continue-player').onclick=()=>{modal.close();if(after) after();else handleInvite();};
      } else {modal.close();if(after)after();}
    } catch(error) {event.target.querySelector('.modal-error').textContent=error.message;button.disabled=false;}
  });
  $('#recover-button')?.addEventListener('click', recoverFlow);
}
function recoverFlow() {
  showModal('<h2>Welcome back.</h2><p>Enter the private recovery key you saved when you created your player. This signs out your previous browser.</p><form id="recover-form"><label for="recovery">Recovery key</label><input id="recovery" required autocomplete="off"><p class="modal-error" role="alert"></p><button class="primary">Restore player ↗</button></form>');
  $('#recover-form').onsubmit=async event=>{event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;try{accept(await api('recover',{key:$('#recovery').value}));modal.close();handleInvite();}catch(error){event.target.querySelector('.modal-error').textContent=error.message;button.disabled=false;}};
}
async function start() {
  if(!state?.player) {profileFlow(start);return;}
  if(busy)return;busy=true;$('#start-button').disabled=true;$('#game-message').textContent='';
  try{accept(await api('start',{}));$('#expression').focus();handleInvite();}catch(error){$('#game-message').textContent=error.message;}finally{busy=false;$('#start-button').disabled=false;}
}
function groupFlow(join=false, code='') {
  if(!state?.player){profileFlow(()=>groupFlow(join,code));return;}
  showModal(`<span class="eyebrow">YOUR DAILY RIVALRY</span><h2>${join?'Join your friends.':'Start a friend circle.'}</h2><p>${join?'Enter an invite code to compare your daily results.':'Everyone in the group can see each other’s names and scores. Solutions appear after solving.'}</p><form id="group-form"><label for="group-input">${join?'Invite code':'Group name'}</label><input id="group-input" maxlength="${join?12:32}" required value="${escapeHTML(code)}" placeholder="${join?'12-character code':'The mental math club'}"><p class="modal-error" role="alert"></p><button class="primary">${join?'Join group':'Create group'} <span>↗</span></button></form>`);
  $('#group-form').onsubmit=async event=>{
    event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;
    const value=$('#group-input').value, priorIds=new Set((state.clubs||[]).map(c=>c.id));
    try{
      const result=await api(join?'join':'clubs',join?{code:value}:{name:value});
      selectedClub=join?value.trim().toUpperCase():result.clubs.find(c=>!priorIds.has(c.id))?.id||'';
      accept(result);modal.close();inviteCode='';history.replaceState(null,'',location.pathname);toast(join?'You joined the circle.':'Group created. Copy the invite to bring your friends.');
    }catch(error){event.target.querySelector('.modal-error').textContent=error.message;button.disabled=false;}
  };
}
function handleInvite() {
  if(inviteCode && state?.player && !modal.open) {
    if(state.clubs?.some(c=>c.id===inviteCode.toUpperCase())) {selectedClub=inviteCode.toUpperCase();renderBoard();inviteCode='';history.replaceState(null,'',location.pathname);}
    else groupFlow(true,inviteCode);
  }
}
async function copyText(text,message='Copied!') {
  try{await navigator.clipboard.writeText(text);toast(message);}catch{showModal(`<h2>Copy and share.</h2><p>Clipboard access isn’t available here. Select the text below to copy it.</p><code class="recovery-key">${escapeHTML(text)}</code>`);}
}
function shareResult() {
  const club=state.clubs?.find(c=>c.id===selectedClub);
  const url=location.origin+(club?'/?join='+encodeURIComponent(club.id):'/');
  copyText(`Twentyfourdle · ${state.day}\n🟩 🟩 🟩 🟩 = 24\n⏱ ${timeLabel(state.attempt.elapsed)} · ${state.attempt.best_score} simplicity points${state.attempt.best_score===state.optimal.score?' ✨ optimal':''}\nCan you beat my time?\n${url}`,'Spoiler-free result copied!');
}
$('#start-button').onclick=start;
$('#help-button').onclick=showHelp;
$('#scoring-button').onclick=showScoring;
$('#profile-button').onclick=()=>profileFlow();
$('#create-button').onclick=()=>groupFlow();
$('#join-button').onclick=()=>groupFlow(true);
$('#close-modal').onclick=()=>modal.close();
modal.addEventListener('click',event=>{if(event.target===modal){const r=modal.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)modal.close();}});
$('#club-select').onchange=event=>{selectedClub=event.target.value;renderBoard();};
$('#invite-button').onclick=()=>copyText(location.origin+'/?join='+encodeURIComponent(selectedClub),'Group invite copied!');
for(const button of document.querySelectorAll('[data-ranking]')) {
  button.onclick=()=>{ranking=button.dataset.ranking;for(const tab of document.querySelectorAll('[data-ranking]')){const selected=tab===button;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;}$('#leaderboard').setAttribute('aria-labelledby',button.id);renderBoard();};
  button.onkeydown=event=>{if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();const other=button.id==='speed-tab'?$('#simple-tab'):$('#speed-tab');other.click();other.focus();}};
}
for(const button of document.querySelectorAll('[data-token]'))button.onclick=()=>insert(button.dataset.token);
$('#clear').onclick=()=>{$('#expression').value='';$('#expression').focus();};
$('#backspace').onclick=()=>{const input=$('#expression'),start=input.selectionStart,end=input.selectionEnd;input.value=input.value.slice(0,start===end?Math.max(0,start-1):start)+input.value.slice(end);const pos=start===end?Math.max(0,start-1):start;input.focus();input.setSelectionRange(pos,pos);};
$('#solution-form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;busy=true;$('#submit-button').disabled=true;$('#game-message').textContent='';
  const wasSolved=solved(),oldScore=state.attempt?.best_score;
  try{const result=await api('submit',{day:state.day,expression:$('#expression').value});editing=false;accept(result);toast(!wasSolved?'You made 24!':result.attempt.best_score<oldScore?'A simpler solution. Nice!':'Correct! Your simplest solution is still saved.');}
  catch(error){$('#game-message').textContent=error.message;}
  finally{busy=false;$('#submit-button').disabled=false;}
};
async function refresh() {
  if(busy||document.hidden)return;
  try{const value=await api('state');accept(value);$('#board-message').textContent='';handleInvite();}
  catch{ $('#board-message').textContent='Updates paused. Reconnecting shortly…'; }
}
async function initialize(){try{accept(await api('state'));handleInvite();}catch(error){$('#game-message').textContent=error.message;$('#start-button').disabled=false;$('#start-button').textContent='Retry connection';$('#start-button').onclick=()=>{initialize();$('#start-button').onclick=start;};}}
initialize();setInterval(updateClocks,100);setInterval(refresh,15000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
